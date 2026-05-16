from __future__ import annotations

import mimetypes
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

_ALLOWED_TYPES: frozenset[str] = frozenset(getattr(settings, "ALLOWED_UPLOAD_MIME_TYPES", set()))
_ALLOWED_EXTS: frozenset[str] = frozenset(getattr(settings, "ALLOWED_UPLOAD_EXTENSIONS", set()))
_MAX_BYTES: int = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 10 * 1024 * 1024)


def _validate_upload(file) -> str | None:
    """Return an error message string, or None if the file is acceptable."""
    if file.size > _MAX_BYTES:
        mb = _MAX_BYTES // (1024 * 1024)
        return f"File exceeds the maximum allowed size of {mb} MB."

    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
    if not ext or ext not in _ALLOWED_EXTS:
        return f"File extension '.{ext}' is not allowed."

    # Resolve content-type: prefer what Django sniffed from the stream over
    # the client-supplied header (which can be spoofed).
    sniffed = mimetypes.guess_type(file.name)[0] or ""
    client_ct = (file.content_type or "").split(";")[0].strip().lower()
    resolved_ct = sniffed.lower() if sniffed else client_ct

    if resolved_ct not in _ALLOWED_TYPES:
        return f"Content type '{resolved_ct}' is not allowed."

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

        ext = file.name.rsplit(".", 1)[-1].lower()
        path = f"uploads/{uuid.uuid4()}.{ext}"
        sniffed = mimetypes.guess_type(file.name)[0]
        content_type = sniffed or (file.content_type or "application/octet-stream")

        try:
            default_storage.save(path, ContentFile(file.read()))
        except Exception as exc:
            return Response(
                {"detail": f"Storage upload failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        public_url = f"{settings.MEDIA_URL}{path}"
        obj = FileObject.objects.create(
            bucket="local",
            path=path,
            public_url=public_url,
            content_type=content_type,
            size_bytes=file.size,
            uploaded_by=request.user,
        )
        return Response(FileObjectSerializer(obj).data, status=status.HTTP_201_CREATED)


class FileDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, pk: int) -> Response:
        # Only fetch non-deleted records; already-deleted files are treated as gone.
        try:
            obj = FileObject.objects.get(pk=pk, deleted_at__isnull=True)
        except FileObject.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Only the uploader or counselor/admin may delete a file.
        user = request.user
        is_owner = obj.uploaded_by_id == user.pk
        is_privileged = getattr(user, "role", None) in (Role.COUNSELOR, Role.ADMIN)
        if not is_owner and not is_privileged:
            return Response(status=status.HTTP_403_FORBIDDEN)

        # Soft-delete: stamp deleted_at, keep DB record and Supabase file intact
        # so the URL and audit history remain queryable.
        obj.deleted_at = timezone.now()
        obj.save(update_fields=["deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
