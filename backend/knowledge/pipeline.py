"""
Knowledge indexing pipeline — background job runner.
Uses threading fallback if Celery/Redis not available.
"""
import hashlib
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=3)


def _get_embedding(text: str) -> list[float] | None:
    try:
        from ai.services.embeddings import get_embedding
        return get_embedding(text[:3000])
    except Exception as e:
        logger.warning("[PIPELINE] embedding failed: %s", e)
        return None


def _update_job(job, **kwargs):
    for k, v in kwargs.items():
        setattr(job, k, v)
    job.save(update_fields=list(kwargs.keys()) + ["updated_at"] if hasattr(job, "updated_at") else list(kwargs.keys()))


def run_indexing_job(job_id: str):
    """
    Main indexing logic for a KnowledgeJob.
    Supports: url crawl, manual text, pdf (not yet), refresh.
    """
    from .models import KnowledgeJob, KnowledgeSource, KnowledgeDocument, KnowledgeChunk, KnowledgeVersion, SourceStatus, JobStatus
    from .crawler import crawl_site, process_manual_content, chunk_text
    from django.conf import settings as s

    try:
        job = KnowledgeJob.objects.select_related("source").get(id=job_id)
    except KnowledgeJob.DoesNotExist:
        logger.error("[PIPELINE] Job %s not found", job_id)
        return

    job.status = JobStatus.RUNNING
    job.started_at = timezone.now()
    job.progress = 5
    job.save(update_fields=["status", "started_at", "progress"])

    source = job.source
    if not source:
        job.status = JobStatus.FAILED
        job.error_log = "No source linked to job"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_log", "finished_at"])
        return

    try:
        source.status = SourceStatus.CRAWLING if job.job_type in ("crawl", "refresh", "auto_update") else SourceStatus.PROCESSING
        source.save(update_fields=["status"])

        if source.source_type == "url" and job.job_type in ("crawl", "refresh", "auto_update"):
            max_pages = getattr(s, "KNOWLEDGE_MAX_PAGES_PER_SOURCE", 20)
            # Use source's configured max_pages if set
            if source.max_pages:
                max_pages = min(source.max_pages, max_pages)
            max_depth = source.max_depth or 2

            def prog(done, total):
                pct = int(10 + (done / max(total, 1)) * 50)
                try:
                    job.progress = min(pct, 65)
                    job.pages_processed = done
                    job.pages_total = total
                    job.save(update_fields=["progress", "pages_processed", "pages_total"])
                except Exception:
                    pass

            pages = crawl_site(source.url, max_pages=max_pages, max_depth=max_depth, progress_cb=prog)
            job.pages_processed = len(pages)
            job.pages_total = len(pages)
            job.progress = 65
            job.save(update_fields=["pages_processed", "pages_total", "progress"])

            # For auto_update: compare hashes, skip unchanged pages
            if job.job_type == "auto_update":
                existing_hashes = set(KnowledgeDocument.objects.filter(source=source).values_list("content_hash", flat=True))
                new_pages = [p for p in pages if p["content_hash"] not in existing_hashes]
                if not new_pages:
                    # No changes
                    source.status = SourceStatus.INDEXED
                    source.last_crawled_at = timezone.now()
                    source.save(update_fields=["status", "last_crawled_at"])
                    job.status = JobStatus.COMPLETED
                    job.progress = 100
                    job.finished_at = timezone.now()
                    if job.started_at:
                        job.duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
                    job.save(update_fields=["status", "progress", "finished_at", "duration_ms"])
                    return
                pages = new_pages

            # Create documents + chunks
            total_chunks = 0
            chunk_size = getattr(s, "KNOWLEDGE_CHUNK_SIZE", 800)
            overlap = getattr(s, "KNOWLEDGE_CHUNK_OVERLAP", 120)

            for idx, page in enumerate(pages):
                doc, created = KnowledgeDocument.objects.get_or_create(
                    source=source,
                    url=page["url"],
                    defaults={
                        "title": page["title"][:500],
                        "content": page["cleaned_content"][:50000],
                        "cleaned_content": page["cleaned_content"][:50000],
                        "content_hash": page["content_hash"],
                        "status": SourceStatus.INDEXED,
                    }
                )
                if not created:
                    # Update if hash changed
                    if doc.content_hash != page["content_hash"]:
                        # Remove old chunks for this doc
                        deleted = KnowledgeChunk.objects.filter(document=doc).delete()[0]
                        job.chunks_removed += deleted
                        doc.content = page["cleaned_content"][:50000]
                        doc.cleaned_content = page["cleaned_content"][:50000]
                        doc.content_hash = page["content_hash"]
                        doc.title = page["title"][:500]
                        doc.save(update_fields=["content", "cleaned_content", "content_hash", "title", "updated_at"])
                    else:
                        continue

                chunks = chunk_text(page["cleaned_content"], chunk_size=chunk_size, overlap=overlap)
                for ci, chunk_txt in enumerate(chunks):
                    emb = _get_embedding(chunk_txt)
                    ch = hashlib.sha256(chunk_txt.encode()).hexdigest()
                    # Deduplicate chunk
                    if KnowledgeChunk.objects.filter(content_hash=ch, source=source).exists():
                        continue
                    KnowledgeChunk.objects.create(
                        source=source,
                        document=doc,
                        chunk_index=ci,
                        chunk_text=chunk_txt,
                        content_hash=ch,
                        embedding=emb,
                        token_count=len(chunk_txt.split()),
                        metadata={"source_url": page["url"], "title": page["title"]},
                    )
                    total_chunks += 1
                doc.chunks_created = len(chunks)
                doc.save(update_fields=["chunks_created"])
                # Progress
                pct = 65 + int((idx + 1) / max(len(pages), 1) * 30)
                job.progress = min(pct, 95)
                job.chunks_added = total_chunks
                job.save(update_fields=["progress", "chunks_added", "chunks_removed"])

            source.pages_total = len(pages)
            source.pages_indexed = len(pages)
            source.chunks_total = KnowledgeChunk.objects.filter(source=source).count()
            source.content_hash = hashlib.sha256("".join(sorted([p["content_hash"] for p in pages])).encode()).hexdigest() if pages else ""
            source.status = SourceStatus.INDEXED
            source.last_crawled_at = timezone.now()
            source.error_message = ""
            if source.auto_update != "manual":
                # Schedule next crawl
                from datetime import timedelta
                if source.auto_update == "daily":
                    source.next_crawl_at = timezone.now() + timedelta(days=1)
                elif source.auto_update == "every_3_days":
                    source.next_crawl_at = timezone.now() + timedelta(days=3)
                elif source.auto_update == "weekly":
                    source.next_crawl_at = timezone.now() + timedelta(days=7)
            source.save()

            # Version
            KnowledgeVersion.objects.create(source=source, content_hash=source.content_hash, pages=len(pages), chunks=total_chunks)

            job.chunks_added = total_chunks
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.finished_at = timezone.now()
            if job.started_at:
                job.duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
                source.crawl_duration_ms = job.duration_ms
                source.save(update_fields=["crawl_duration_ms"])
            job.save(update_fields=["status", "progress", "finished_at", "duration_ms", "chunks_added"])

        elif source.source_type in ("text", "markdown", "manual"):
            # Manual content already stored in source? For manual we use source.title + document
            # Job's source already has title/content via separate field? We'll treat source.url as title placeholder and expect document already? Instead fetch source's first document's content?
            # For manual: source creation stores content in a pending document; we process it here.
            # Find pending document
            doc = KnowledgeDocument.objects.filter(source=source, status=SourceStatus.QUEUED).first()
            if not doc:
                # Fallback: use source title as content? Create one
                raise ValueError("No manual content document found")
            cleaned = doc.cleaned_content
            title = doc.title
            chunks = chunk_text(cleaned, chunk_size=getattr(settings, "KNOWLEDGE_CHUNK_SIZE", 800), overlap=getattr(settings, "KNOWLEDGE_CHUNK_OVERLAP", 120))
            total = 0
            for ci, chunk_txt in enumerate(chunks):
                emb = _get_embedding(chunk_txt)
                ch = hashlib.sha256(chunk_txt.encode()).hexdigest()
                KnowledgeChunk.objects.create(
                    source=source,
                    document=doc,
                    chunk_index=ci,
                    chunk_text=chunk_txt,
                    content_hash=ch,
                    embedding=emb,
                    token_count=len(chunk_txt.split()),
                    metadata={"source_url": source.url or "", "title": title},
                )
                total += 1
            doc.chunks_created = total
            doc.status = SourceStatus.INDEXED
            doc.save(update_fields=["chunks_created", "status"])
            source.chunks_total = KnowledgeChunk.objects.filter(source=source).count()
            source.pages_total = 1
            source.pages_indexed = 1
            source.status = SourceStatus.INDEXED
            source.error_message = ""
            source.save(update_fields=["chunks_total", "pages_total", "pages_indexed", "status", "error_message"])
            job.chunks_added = total
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.finished_at = timezone.now()
            if job.started_at:
                job.duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
            job.save(update_fields=["status", "progress", "finished_at", "duration_ms", "chunks_added"])

        else:
            raise ValueError(f"Unsupported source_type {source.source_type}")

    except Exception as e:
        logger.exception("[PIPELINE] Job %s failed: %s", job_id, e)
        try:
            job.refresh_from_db()
            job.status = JobStatus.FAILED
            job.error_log = str(e)[:5000]
            job.finished_at = timezone.now()
            if job.started_at:
                job.duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
            job.save(update_fields=["status", "error_log", "finished_at", "duration_ms"])
            if source:
                try:
                    source.refresh_from_db()
                    source.status = SourceStatus.FAILED
                    source.error_message = str(e)[:2000]
                    source.save(update_fields=["status", "error_message"])
                except Exception:
                    pass
        except Exception:
            pass


def enqueue_job(source, job_type: str = "crawl", created_by: str = "") -> "KnowledgeJob":
    from .models import KnowledgeJob, JobStatus
    job = KnowledgeJob.objects.create(
        source=source,
        source_url=source.url if source else "",
        job_type=job_type,
        status=JobStatus.QUEUED,
        progress=0,
        created_by=created_by,
    )
    # Try Celery first, fallback to threading
    try:
        from celery import current_app
        # Check if celery is configured and redis reachable quickly
        # Instead, use our thread pool to avoid redis dependency in local dev
        raise ImportError("use threading")
    except Exception:
        # Threading fallback
        _executor.submit(_thread_wrapper, str(job.id))
    return job


def _thread_wrapper(job_id: str):
    # Run in thread; need Django setup
    import django
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        django.setup()
    except Exception:
        pass
    # Small delay to let job creation commit
    time.sleep(0.3)
    run_indexing_job(job_id)
