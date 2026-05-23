"""
File upload and delete API views.

All uploads are stored on the local filesystem via Django's default_storage
(configured to FileSystemStorage → MEDIA_ROOT). In production, ensure
MEDIA_ROOT is on a persistent volume.
"""
from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import Role

from .models import FileObject
from .serializers import FileObjectSerializer

logger = logging.getLogger(__name__)

_ALLOWED_EXTS: frozenset[str] = frozenset(getattr(settings, "ALLOWED_UPLOAD_EXTENSIONS", set()))
_MAX_BYTES: int = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024)


def _validate_upload(file) -> str | None:
    """Return an error message string, or None if the file passes validation."""
    if file.size > _MAX_BYTES:
        mb = _MAX_BYTES // (1024 * 1024)
        return f"File exceeds the maximum allowed size of {mb} MB."

    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
    if not ext or ext not in _ALLOWED_EXTS:
        return f"File extension '.{ext}' is not allowed."

    return None


class FileUploadView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        error = _validate_upload(file)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        file_bytes = file.read()

        # Content-level security scan before persisting.
        from apps.common.security.file_scanner import scan_file
        scan_result = scan_file(file_bytes=file_bytes, filename=file.name)
        if not scan_result.safe:
            logger.warning(
                "Upload blocked — malware/dangerous content detected: %s | user=%s",
                scan_result.reason,
                request.user.pk,
            )
            return Response(
                {"detail": f"File rejected: {scan_result.reason}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        import mimetypes
        content_type = mimetypes.guess_type(file.name)[0] or (file.content_type or "application/octet-stream")
        ext = file.name.rsplit(".", 1)[-1].lower()

        try:
            path = f"uploads/{uuid.uuid4()}.{ext}"
            default_storage.save(path, ContentFile(file_bytes))
            public_url = f"{settings.MEDIA_URL}{path}"
        except Exception as exc:
            logger.error("Upload storage failure for user %s: %s", request.user.pk, exc)
            return Response(
                {"detail": "Storage upload failed."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        obj = FileObject.objects.create(
            bucket="local",
            path=path,
            public_url=public_url,
            content_type=content_type,
            size_bytes=file.size,
            uploaded_by=request.user,
        )
        logger.info("File uploaded: pk=%s path=%s user=%s", obj.pk, path, request.user.pk)
        return Response(FileObjectSerializer(obj).data, status=status.HTTP_201_CREATED)


class FileDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, pk: int) -> Response:
        try:
            obj = FileObject.objects.get(pk=pk, deleted_at__isnull=True)
        except FileObject.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_owner = obj.uploaded_by_id == user.pk
        is_privileged = getattr(user, "role", None) in (Role.COUNSELOR, Role.ADMIN)
        if not is_owner and not is_privileged:
            return Response(status=status.HTTP_403_FORBIDDEN)

        # Soft-delete: preserve DB record for audit history.
        obj.deleted_at = timezone.now()
        obj.save(update_fields=["deleted_at"])
        logger.info("File soft-deleted: pk=%s by user=%s", pk, user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
