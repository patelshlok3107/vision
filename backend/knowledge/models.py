"""
VISION Knowledge Engine — RAG system models.

Tables (spec §20):
  knowledge_sources, knowledge_documents, knowledge_chunks,
  knowledge_jobs, knowledge_versions, admin_activity, admin_sessions
Also reuses existing auth user tables.
"""
import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

class SourceStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    CRAWLING = "crawling", "Crawling"
    PROCESSING = "processing", "Processing"
    INDEXING = "indexing", "Indexing"
    INDEXED = "indexed", "Indexed"
    FAILED = "failed", "Failed"
    UPDATING = "updating", "Updating"


class AutoUpdateChoice(models.TextChoices):
    MANUAL = "manual", "Manual"
    DAILY = "daily", "Daily"
    EVERY_3_DAYS = "every_3_days", "Every 3 days"
    WEEKLY = "weekly", "Weekly"


class SourceType(models.TextChoices):
    URL = "url", "Website URL"
    TEXT = "text", "Text"
    MARKDOWN = "markdown", "Markdown"
    PDF = "pdf", "PDF"
    MANUAL = "manual", "Manual"


class KnowledgeSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.URLField(max_length=2000, blank=True)
    domain = models.CharField(max_length=255, blank=True, db_index=True)
    title = models.CharField(max_length=500, blank=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.URL)
    status = models.CharField(max_length=20, choices=SourceStatus.choices, default=SourceStatus.QUEUED, db_index=True)

    # Stats
    pages_total = models.PositiveIntegerField(default=0)
    pages_indexed = models.PositiveIntegerField(default=0)
    failed_pages = models.PositiveIntegerField(default=0)
    chunks_total = models.PositiveIntegerField(default=0)

    # Hash / error
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    error_message = models.TextField(blank=True)
    crawl_duration_ms = models.PositiveIntegerField(null=True, blank=True)

    # Scheduling
    auto_update = models.CharField(max_length=20, choices=AutoUpdateChoice.choices, default=AutoUpdateChoice.MANUAL)
    last_crawled_at = models.DateTimeField(null=True, blank=True)
    next_crawl_at = models.DateTimeField(null=True, blank=True)

    # Limits
    max_pages = models.PositiveSmallIntegerField(default=50)
    max_depth = models.PositiveSmallIntegerField(default=2)

    # Metadata
    category = models.CharField(max_length=100, blank=True, default="general")
    tags = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.CharField(max_length=150, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "knowledge_sources"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "is_active"]),
            models.Index(fields=["domain"]),
        ]

    def __str__(self):
        return f"{self.domain or self.url or self.title} [{self.status}]"

    @staticmethod
    def make_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Document (per-page)
# ---------------------------------------------------------------------------

class KnowledgeDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(KnowledgeSource, on_delete=models.CASCADE, related_name="documents", db_index=True)
    url = models.URLField(max_length=2000)
    title = models.CharField(max_length=500, blank=True)
    content = models.TextField(blank=True)
    cleaned_content = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=SourceStatus.choices, default=SourceStatus.QUEUED)
    chunks_created = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    crawl_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "status"]),
            models.Index(fields=["content_hash"]),
        ]

    def __str__(self):
        return f"Doc {self.url[:60]}"


# ---------------------------------------------------------------------------
# Chunk (vector)
# ---------------------------------------------------------------------------

class KnowledgeChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(KnowledgeSource, on_delete=models.CASCADE, related_name="chunks", db_index=True)
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks", null=True, blank=True, db_index=True)
    chunk_index = models.PositiveIntegerField(default=0)
    chunk_text = models.TextField()
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    embedding = models.JSONField(null=True, blank=True)
    token_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "knowledge_chunks"
        ordering = ["source", "chunk_index"]
        indexes = [
            models.Index(fields=["source", "chunk_index"]),
            models.Index(fields=["content_hash"]),
        ]

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.source_id}"


# ---------------------------------------------------------------------------
# Version tracking (hash history per source)
# ---------------------------------------------------------------------------

class KnowledgeVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(KnowledgeSource, on_delete=models.CASCADE, related_name="versions", db_index=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    pages = models.PositiveIntegerField(default=0)
    chunks = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "knowledge_versions"
        ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class JobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class JobType(models.TextChoices):
    CRAWL = "crawl", "Crawl"
    REFRESH = "refresh", "Refresh"
    MANUAL = "manual", "Manual"
    AUTO_UPDATE = "auto_update", "Auto Update"
    DELETE = "delete", "Delete"


class KnowledgeJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(KnowledgeSource, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs", db_index=True)
    source_url = models.CharField(max_length=2000, blank=True)
    job_type = models.CharField(max_length=20, choices=JobType.choices, default=JobType.CRAWL)
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)

    pages_processed = models.PositiveIntegerField(default=0)
    pages_total = models.PositiveIntegerField(default=0)
    chunks_added = models.PositiveIntegerField(default=0)
    chunks_updated = models.PositiveIntegerField(default=0)
    chunks_removed = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_log = models.TextField(blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "knowledge_jobs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self):
        return f"Job {self.job_type} {self.status} {self.progress}%"


# ---------------------------------------------------------------------------
# Admin activity
# ---------------------------------------------------------------------------

class AdminActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin_username = models.CharField(max_length=150, db_index=True)
    action = models.CharField(max_length=100, db_index=True)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, default="success")
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "admin_activity"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.admin_username} {self.action} @ {self.created_at}"


# ---------------------------------------------------------------------------
# Admin session (optional tracking)
# ---------------------------------------------------------------------------

class AdminSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin_username = models.CharField(max_length=150)
    jti = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_valid = models.BooleanField(default=True)

    class Meta:
        db_table = "admin_sessions"
        ordering = ["-created_at"]
