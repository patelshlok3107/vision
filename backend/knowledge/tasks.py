import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


def check_auto_updates():
    """Called periodically (e.g., via cron) to enqueue auto-update jobs for due sources."""
    from .models import KnowledgeSource
    now = timezone.now()
    due = KnowledgeSource.objects.filter(next_crawl_at__lte=now, is_active=True).exclude(auto_update="manual")
    for src in due:
        # Skip if already running
        if src.status in ("crawling", "processing", "indexing", "updating", "queued"):
            continue
        try:
            from .pipeline import enqueue_job
            job = enqueue_job(src, job_type="auto_update", created_by="scheduler")
            logger.info("[AUTO_UPDATE] Enqueued %s job %s", src.domain, job.id)
        except Exception as e:
            logger.warning("[AUTO_UPDATE] Failed to enqueue %s: %s", src.id, e)
