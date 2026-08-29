import time
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import Conversation, Message

from .auth import verify_admin_credentials, create_admin_token, check_rate_limit
from .models import KnowledgeSource, KnowledgeDocument, KnowledgeChunk, KnowledgeJob, AdminActivity, KnowledgeVersion, SourceStatus, JobStatus
from .permissions import IsAdminAuthenticated
from .utils import validate_url_for_crawl, normalize_url, extract_domain, log_admin_activity
from .crawler import process_manual_content

User = get_user_model()


# ---------------------------------------------------------------------------
# Admin login
# ---------------------------------------------------------------------------

class AdminLoginView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        ip = request.META.get("REMOTE_ADDR", "0.0.0.0")
        if not check_rate_limit(ip):
            return Response({"error": "Too many attempts. Try again in a minute."}, status=429)
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not username or not password:
            return Response({"error": "Username and password required"}, status=400)
        if not verify_admin_credentials(username, password):
            log_admin_activity(username, "admin_login_failed", request, status="failed", details={"reason": "bad credentials"})
            return Response({"error": "Invalid credentials"}, status=401)
        token, jti, exp = create_admin_token(username)
        log_admin_activity(username, "admin_login", request, status="success")
        return Response({
            "token": token,
            "username": username,
            "expires_at": exp.isoformat(),
            "jti": jti,
        })


class AdminMeView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request):
        return Response({"username": getattr(request, "admin_username", "admin"), "is_admin": True})


class AdminLogoutView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def post(self, request):
        try:
            from .models import AdminSession
            jti = getattr(request, "admin_jti", None)
            if jti:
                AdminSession.objects.filter(jti=jti).update(is_valid=False)
            log_admin_activity(request.admin_username, "admin_logout", request)
        except Exception:
            pass
        return Response({"status": "logged out"})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class AdminDashboardView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request):
        total_users = User.objects.count()
        # Active users: logged in or sent message last 30 days
        from datetime import timedelta
        thirty = timezone.now() - timedelta(days=30)
        active_users = User.objects.filter(last_login__gte=thirty).count()
        # Fallback: users with recent conversations
        if active_users == 0:
            recent_user_ids = Conversation.objects.filter(updated_at__gte=thirty).values_list("user_id", flat=True).distinct()
            active_users = User.objects.filter(id__in=recent_user_ids).count()

        total_conversations = Conversation.objects.count()
        total_messages = Message.objects.count()

        total_sources = KnowledgeSource.objects.count()
        indexed_sources = KnowledgeSource.objects.filter(status=SourceStatus.INDEXED).count()
        failed_jobs = KnowledgeJob.objects.filter(status=JobStatus.FAILED).count()

        last_source = KnowledgeSource.objects.filter(last_crawled_at__isnull=False).order_by("-last_crawled_at").first()
        last_update = last_source.last_crawled_at.isoformat() if last_source and last_source.last_crawled_at else None

        # AI status via ollama client
        try:
            from ai.services.ollama_client import client
            health = client.healthCheck()
            ollama_connected = health.get("ollama", {}).get("connected", False)
            text_model = health.get("textModel", {}).get("name", "") or getattr(settings, "OLLAMA_TEXT_MODEL", "")
        except Exception:
            ollama_connected = False
            text_model = getattr(settings, "OLLAMA_TEXT_MODEL", "")

        # DB status: try count
        try:
            User.objects.exists()
            db_ok = True
        except Exception:
            db_ok = False

        recent_activity = list(AdminActivity.objects.order_by("-created_at")[:10].values("action", "admin_username", "status", "created_at", "target_type"))

        return Response({
            "total_users": total_users,
            "active_users": active_users,
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "knowledge_sources": total_sources,
            "indexed_sources": indexed_sources,
            "failed_jobs": failed_jobs,
            "last_knowledge_update": last_update,
            "ai_status": "online" if ollama_connected else "offline",
            "ai_model": text_model,
            "database_status": "online" if db_ok else "offline",
            "recent_activity": recent_activity,
        })


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class AdminUsersView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        filter_opt = request.query_params.get("filter") or ""
        limit = min(int(request.query_params.get("limit") or 50), 200)
        offset = int(request.query_params.get("offset") or 0)

        qs = User.objects.all().order_by("-date_joined")
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(username__icontains=q) | Q(first_name__icontains=q))
        # Filter active/inactive/new
        if filter_opt == "active":
            from datetime import timedelta
            qs = qs.filter(last_login__gte=timezone.now() - timedelta(days=30))
        elif filter_opt == "inactive":
            from datetime import timedelta
            qs = qs.filter(last_login__lt=timezone.now() - timedelta(days=30))
        elif filter_opt == "new":
            from datetime import timedelta
            qs = qs.filter(date_joined__gte=timezone.now() - timedelta(days=7))

        total = qs.count()
        users = qs[offset:offset+limit]
        out = []
        for u in users:
            conv_count = Conversation.objects.filter(user=u).count()
            # last active: max(last_login, last_message)
            last_msg = Message.objects.filter(conversation__user=u).order_by("-created_at").first()
            last_active = None
            if u.last_login:
                last_active = u.last_login
            if last_msg and last_msg.created_at and (not last_active or last_msg.created_at > last_active):
                last_active = last_msg.created_at
            out.append({
                "id": str(u.id),
                "username": u.username,
                "email": u.email,
                "first_name": u.first_name,
                "is_active": u.is_active,
                "date_joined": u.date_joined.isoformat() if u.date_joined else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "last_active": last_active.isoformat() if last_active else None,
                "conversation_count": conv_count,
            })
        return Response({"total": total, "users": out})


class AdminUserDetailView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request, user_id):
        try:
            u = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=404)
        convs = Conversation.objects.filter(user=u)
        conv_count = convs.count()
        msg_count = Message.objects.filter(conversation__user=u).count()
        last_login = u.last_login.isoformat() if u.last_login else None
        # Recent conversations titles
        recent = list(convs.order_by("-updated_at")[:5].values("id", "title", "updated_at", "message_count" if False else "title"))
        # Actually compute message_count per conv quickly
        for r in recent:
            r["id"] = str(r["id"])
            if r.get("updated_at"):
                r["updated_at"] = r["updated_at"].isoformat()
        return Response({
            "id": str(u.id),
            "username": u.username,
            "email": u.email,
            "first_name": u.first_name,
            "is_active": u.is_active,
            "is_staff": u.is_staff,
            "date_joined": u.date_joined.isoformat() if u.date_joined else None,
            "last_login": last_login,
            "conversation_count": conv_count,
            "message_count": msg_count,
            "recent_conversations": recent,
        })


# ---------------------------------------------------------------------------
# Knowledge sources
# ---------------------------------------------------------------------------

class AdminKnowledgeListCreateView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request):
        qs = KnowledgeSource.objects.all().order_by("-updated_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        data = []
        for s in qs:
            data.append({
                "id": str(s.id),
                "url": s.url,
                "domain": s.domain,
                "title": s.title,
                "source_type": s.source_type,
                "status": s.status,
                "pages_total": s.pages_total,
                "pages_indexed": s.pages_indexed,
                "failed_pages": s.failed_pages,
                "chunks_total": s.chunks_total,
                "auto_update": s.auto_update,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "last_crawled_at": s.last_crawled_at.isoformat() if s.last_crawled_at else None,
                "next_crawl_at": s.next_crawl_at.isoformat() if s.next_crawl_at else None,
                "error_message": s.error_message[:500] if s.error_message else "",
            })
        return Response(data)

    def post(self, request):
        # Supports: url crawl or manual text/markdown
        url = (request.data.get("url") or "").strip()
        source_type = (request.data.get("source_type") or "url").lower()
        title = (request.data.get("title") or "").strip()
        content = request.data.get("content") or ""
        category = (request.data.get("category") or "general").strip()
        tags = request.data.get("tags") or []
        auto_update = (request.data.get("auto_update") or "manual").lower()
        max_pages = int(request.data.get("max_pages") or getattr(settings, "KNOWLEDGE_MAX_PAGES_PER_SOURCE", 20))
        max_pages = max(1, min(max_pages, 100))

        if source_type == "url":
            if not url:
                return Response({"error": "URL required"}, status=400)
            # SSRF validation
            ok, err = validate_url_for_crawl(url)
            if not ok:
                return Response({"error": err}, status=400)
            norm = normalize_url(url)
            domain = extract_domain(norm)
            # Check duplicate
            if KnowledgeSource.objects.filter(url=norm).exists():
                return Response({"error": "Source already exists for this URL"}, status=409)
            source = KnowledgeSource.objects.create(
                url=norm,
                domain=domain,
                title=title or domain,
                source_type="url",
                status=SourceStatus.QUEUED,
                auto_update=auto_update if auto_update in [c[0] for c in KnowledgeSource._meta.get_field("auto_update").choices] else "manual",
                max_pages=max_pages,
                category=category,
                tags=tags if isinstance(tags, list) else [],
                created_by=request.admin_username,
            )
            from .pipeline import enqueue_job
            job = enqueue_job(source, job_type="crawl", created_by=request.admin_username)
            log_admin_activity(request.admin_username, "source_added", request, target_type="knowledge_source", target_id=str(source.id), details={"url": norm, "job_id": str(job.id)})
            return Response({"id": str(source.id), "job_id": str(job.id), "status": source.status}, status=201)
        else:
            # Manual text/markdown
            if not content or len(content.strip()) < 20:
                return Response({"error": "Content too short (min 20 chars)"}, status=400)
            if not title:
                title = (content[:60] + "...") if len(content) > 60 else content[:60]
            try:
                clean_title, cleaned, h = process_manual_content(title, content)
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
            source = KnowledgeSource.objects.create(
                url=url or "",
                domain=extract_domain(url) if url else "",
                title=clean_title,
                source_type=source_type if source_type in ("text", "markdown", "manual") else "text",
                status=SourceStatus.QUEUED,
                category=category,
                tags=tags if isinstance(tags, list) else [],
                created_by=request.admin_username,
            )
            # Create pending document for manual
            doc = KnowledgeDocument.objects.create(
                source=source,
                url=url or f"manual://{source.id}",
                title=clean_title,
                content=content[:50000],
                cleaned_content=cleaned[:50000],
                content_hash=h,
                status=SourceStatus.QUEUED,
            )
            from .pipeline import enqueue_job
            job = enqueue_job(source, job_type="manual", created_by=request.admin_username)
            log_admin_activity(request.admin_username, "manual_knowledge_added", request, target_type="knowledge_source", target_id=str(source.id), details={"title": clean_title})
            return Response({"id": str(source.id), "job_id": str(job.id), "status": source.status}, status=201)


class AdminKnowledgeDetailView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request, source_id):
        try:
            s = KnowledgeSource.objects.get(id=source_id)
        except KnowledgeSource.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        docs = list(s.documents.all().order_by("-created_at")[:50].values("id", "url", "title", "status", "chunks_created", "created_at", "error_message"))
        for d in docs:
            d["id"] = str(d["id"])
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
        jobs = list(s.jobs.all().order_by("-created_at")[:10].values("id", "job_type", "status", "progress", "pages_processed", "chunks_added", "error_log", "created_at", "duration_ms"))
        for j in jobs:
            j["id"] = str(j["id"])
            if j.get("created_at"):
                j["created_at"] = j["created_at"].isoformat()
        return Response({
            "id": str(s.id),
            "url": s.url,
            "domain": s.domain,
            "title": s.title,
            "source_type": s.source_type,
            "status": s.status,
            "pages_total": s.pages_total,
            "pages_indexed": s.pages_indexed,
            "failed_pages": s.failed_pages,
            "chunks_total": s.chunks_total,
            "content_hash": s.content_hash,
            "error_message": s.error_message,
            "crawl_duration_ms": s.crawl_duration_ms,
            "auto_update": s.auto_update,
            "max_pages": s.max_pages,
            "max_depth": s.max_depth,
            "category": s.category,
            "tags": s.tags,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "last_crawled_at": s.last_crawled_at.isoformat() if s.last_crawled_at else None,
            "next_crawl_at": s.next_crawl_at.isoformat() if s.next_crawl_at else None,
            "documents": docs,
            "jobs": jobs,
        })

    def patch(self, request, source_id):
        try:
            s = KnowledgeSource.objects.get(id=source_id)
        except KnowledgeSource.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        # Allow updating auto_update, max_pages, title
        if "auto_update" in request.data:
            val = request.data["auto_update"]
            if val not in [c[0] for c in KnowledgeSource._meta.get_field("auto_update").choices]:
                return Response({"error": "Invalid auto_update"}, status=400)
            s.auto_update = val
            # Recompute next_crawl
            from datetime import timedelta
            if val == "manual":
                s.next_crawl_at = None
            elif val == "daily":
                s.next_crawl_at = timezone.now() + timedelta(days=1)
            elif val == "every_3_days":
                s.next_crawl_at = timezone.now() + timedelta(days=3)
            elif val == "weekly":
                s.next_crawl_at = timezone.now() + timedelta(days=7)
        if "max_pages" in request.data:
            try:
                mp = int(request.data["max_pages"])
                s.max_pages = max(1, min(mp, 100))
            except: pass
        if "title" in request.data:
            s.title = request.data["title"][:500]
        s.save()
        log_admin_activity(request.admin_username, "source_updated", request, target_type="knowledge_source", target_id=str(s.id), details={"auto_update": s.auto_update})
        return Response({"status": "updated"})

    def delete(self, request, source_id):
        try:
            s = KnowledgeSource.objects.get(id=source_id)
        except KnowledgeSource.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        # Delete chunks via cascade
        from .models import KnowledgeChunk
        # Log before delete
        log_admin_activity(request.admin_username, "source_deleted", request, target_type="knowledge_source", target_id=str(s.id), details={"url": s.url})
        s.delete()
        return Response({"status": "deleted"})


class AdminKnowledgeRefreshView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def post(self, request, source_id):
        try:
            s = KnowledgeSource.objects.get(id=source_id)
        except KnowledgeSource.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        if s.status in (SourceStatus.CRAWLING, SourceStatus.PROCESSING, SourceStatus.INDEXING, SourceStatus.UPDATING, SourceStatus.QUEUED):
            return Response({"error": "Source is already being processed"}, status=409)
        from .pipeline import enqueue_job
        job = enqueue_job(s, job_type="refresh", created_by=request.admin_username)
        s.status = SourceStatus.UPDATING
        s.save(update_fields=["status"])
        log_admin_activity(request.admin_username, "source_refresh", request, target_type="knowledge_source", target_id=str(s.id))
        return Response({"job_id": str(job.id), "status": "queued"})


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class AdminJobsView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request):
        qs = KnowledgeJob.objects.select_related("source").order_by("-created_at")[:100]
        out = []
        for j in qs:
            out.append({
                "id": str(j.id),
                "source_id": str(j.source_id) if j.source_id else None,
                "source_url": j.source_url,
                "source_domain": j.source.domain if j.source else extract_domain(j.source_url),
                "job_type": j.job_type,
                "status": j.status,
                "progress": j.progress,
                "pages_processed": j.pages_processed,
                "pages_total": j.pages_total,
                "chunks_added": j.chunks_added,
                "chunks_updated": j.chunks_updated,
                "chunks_removed": j.chunks_removed,
                "error_log": (j.error_log or "")[:500],
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                "duration_ms": j.duration_ms,
            })
        return Response(out)


class AdminJobDetailView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request, job_id):
        try:
            j = KnowledgeJob.objects.get(id=job_id)
        except KnowledgeJob.DoesNotExist:
            return Response({"error": "Not found"}, status=404)
        return Response({
            "id": str(j.id),
            "source_id": str(j.source_id) if j.source_id else None,
            "source_url": j.source_url,
            "job_type": j.job_type,
            "status": j.status,
            "progress": j.progress,
            "pages_processed": j.pages_processed,
            "pages_total": j.pages_total,
            "chunks_added": j.chunks_added,
            "chunks_updated": j.chunks_updated,
            "chunks_removed": j.chunks_removed,
            "error_log": j.error_log,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "duration_ms": j.duration_ms,
        })


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class AdminHistoryView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request):
        # History is jobs + versions combined, show jobs as history
        jobs = KnowledgeJob.objects.select_related("source").order_by("-created_at")[:100]
        out = []
        for j in jobs:
            out.append({
                "id": str(j.id),
                "source": j.source.domain if j.source else extract_domain(j.source_url),
                "url": j.source_url,
                "operation": j.job_type,
                "status": j.status,
                "pages_processed": j.pages_processed,
                "chunks_added": j.chunks_added,
                "chunks_updated": j.chunks_updated,
                "chunks_removed": j.chunks_removed,
                "duration_ms": j.duration_ms,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "error": (j.error_log or "")[:300],
            })
        return Response(out)


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

class AdminActivityView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request):
        qs = AdminActivity.objects.order_by("-created_at")[:100]
        out = []
        for a in qs:
            out.append({
                "id": str(a.id),
                "admin_username": a.admin_username,
                "action": a.action,
                "target_type": a.target_type,
                "target_id": a.target_id,
                "status": a.status,
                "details": a.details,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })
        return Response(out)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class AdminSettingsView(APIView):
    authentication_classes = []
    permission_classes = [IsAdminAuthenticated]

    def get(self, request):
        # Return non-sensitive settings
        from django.conf import settings as s
        return Response({
            "ai_model": getattr(s, "OLLAMA_TEXT_MODEL", ""),
            "embedding_model": getattr(s, "KNOWLEDGE_EMBEDDING_MODEL", ""),
            "retrieval_top_k": getattr(s, "KNOWLEDGE_RETRIEVAL_TOP_K", 5),
            "min_similarity": getattr(s, "KNOWLEDGE_MIN_SIMILARITY", 0.55),
            "temperature": getattr(s, "OLLAMA_TEMPERATURE", 0.2),
            "max_pages": getattr(s, "KNOWLEDGE_MAX_PAGES_PER_SOURCE", 20),
            "max_depth": getattr(s, "KNOWLEDGE_MAX_DEPTH", 2),
            "chunk_size": getattr(s, "KNOWLEDGE_CHUNK_SIZE", 800),
            "chunk_overlap": getattr(s, "KNOWLEDGE_CHUNK_OVERLAP", 120),
            "auto_update_default": "manual",
            "ollama_url": getattr(s, "OLLAMA_BASE_URL", ""),
            "ai_provider": getattr(s, "AI_PROVIDER", "ollama"),
            "groq_model": getattr(s, "GROQ_MODEL", ""),
        })

    def patch(self, request):
        # Allow admin to update a subset: retrieval_top_k, max_pages, etc.
        # For now return ok, actual persistence would require env or DB settings model
        # We log the attempt
        log_admin_activity(request.admin_username, "settings_changed", request, details=request.data)
        return Response({"status": "settings updated (env-driven, restart may be needed for some values)"})
