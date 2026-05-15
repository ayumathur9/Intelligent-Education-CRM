from django.conf import settings
from django.db import models


class FileObject(models.Model):
    """
    Metadata for files stored in Supabase Storage.
    deleted_at is set on soft-delete; the Supabase file and URL are preserved.
    """

    bucket = models.CharField(max_length=120)
    path = models.CharField(max_length=512)
    public_url = models.URLField(max_length=1024, blank=True)
    content_type = models.CharField(max_length=200, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __str__(self) -> str:
        return f"{self.bucket}:{self.path}"

