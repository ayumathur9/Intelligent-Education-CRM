from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def list_notifications(request):
    qs = Notification.objects.filter(user=request.user).order_by("-created_at")[:30]
    unread = Notification.objects.filter(user=request.user, read_at__isnull=True).count()
    data = [
        {
            "id": n.pk,
            "title": n.title,
            "message": n.message,
            "read": n.read_at is not None,
            "created_at": n.created_at.strftime("%b %d, %H:%M"),
        }
        for n in qs
    ]
    return JsonResponse({"notifications": data, "unread_count": unread})


@login_required
@require_POST
def mark_read(request, pk):
    Notification.objects.filter(pk=pk, user=request.user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    return JsonResponse({"ok": True})
