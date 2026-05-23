"""
CRIT-1: Authenticated media proxy view.

Replaces the unauthenticated django.views.static.serve for MEDIA_ROOT.
All media access requires a valid session or JWT. Path traversal is
prevented. Ownership is validated for file-tracked uploads.

Nginx integration: set NGINX_MEDIA_ACCEL=1 in env and add the internal
/protected-media/ location to your Nginx config to use X-Accel-Redirect
(zero-copy file serving by Nginx, Django only does the auth check).
"""
from __future__ import annotations

import logging
import mimetypes
import os
import re
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_GET

from apps.users.models import Role

logger = logging.getLogger(__name__)

_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_\-./]+$")


def _safe_resolve(base: Path, rel: str) -> Path | None:
    """Return resolved Path if it stays under base, else None."""
    try:
        resolved = (base / rel).resolve()
        if str(resolved).startswith(str(base.resolve()) + os.sep) or resolved == base.resolve():
            return resolved
    except Exception:
        pass
    return None


@require_GET
def media_proxy(request, path: str) -> HttpResponse:
    """
    Authenticated media file proxy.

    Auth rules:
    - Unauthenticated → 401.
    - Admin / Counselor → full access.
    - Editor / Student → own uploads (FileObject.uploaded_by) only;
      for paths not tracked in FileObject (avatars, cached thumbnails)
      all authenticated users are allowed (internal tool, <50 users).
    - Path traversal → 404.
    """
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

    clean_path = path.strip("/")

    # Reject obviously dangerous paths.
    if not clean_path or ".." in clean_path or not _SAFE_PATH_RE.match(clean_path):
        logger.warning(
            "media_proxy: invalid path from user %s: %r", request.user.pk, path
        )
        raise Http404

    media_root = Path(settings.MEDIA_ROOT)
    full_path = _safe_resolve(media_root, clean_path)
    if full_path is None:
        logger.warning(
            "media_proxy: path traversal attempt from user %s: %r",
            request.user.pk,
            path,
        )
        raise Http404

    if not full_path.exists() or not full_path.is_file():
        raise Http404

    user = request.user

    # Admin and counselors have full read access.
    if user.role not in (Role.ADMIN, Role.COUNSELOR):
        # Uploads tracked in FileObject → enforce uploaded_by ownership.
        if clean_path.startswith("uploads/"):
            from apps.files.models import FileObject
            obj = FileObject.objects.filter(
                path=clean_path, deleted_at__isnull=True
            ).first()
            if obj is not None and obj.uploaded_by_id != user.pk:
                # Editors may access files for students assigned to them.
                if user.role == Role.EDITOR:
                    from apps.crm.models import Student
                    allowed = Student.objects.filter(
                        editor=user, user=obj.uploaded_by
                    ).exists()
                    if not allowed:
                        logger.warning(
                            "media_proxy: editor %s denied access to %s",
                            user.pk,
                            clean_path,
                        )
                        return HttpResponse(status=403)
                else:
                    logger.warning(
                        "media_proxy: user %s (role=%s) denied access to %s",
                        user.pk,
                        user.role,
                        clean_path,
                    )
                    return HttpResponse(status=403)
        # All other paths (profiles/, student_docs/, etc.) — allow any
        # authenticated user. Tighten here if finer-grained control is needed.

    # Nginx X-Accel-Redirect: zero-copy file serving.
    if getattr(settings, "NGINX_MEDIA_ACCEL", False):
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"/protected-media/{clean_path}"
        response["Content-Type"] = ""  # Nginx determines from file extension.
        response["Content-Disposition"] = f'inline; filename="{full_path.name}"'
        return response

    # Fallback: Django streams the file directly.
    content_type, _ = mimetypes.guess_type(str(full_path))
    try:
        f = open(full_path, "rb")
    except OSError:
        raise Http404
    # FileResponse takes ownership of `f` and calls f.close() via response.close().
    # The try/except above ensures we don't leak a handle if open() itself fails.
    return FileResponse(
        f,
        content_type=content_type or "application/octet-stream",
        as_attachment=False,
    )
