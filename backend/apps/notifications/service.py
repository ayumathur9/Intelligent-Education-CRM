from .models import Notification


def create_notification(user, title: str, message: str = "") -> Notification:
    return Notification.objects.create(user=user, title=title, message=message)


async def push_ws(channel_layer, notification, link: str = "") -> None:
    """Push a notification over WebSocket from async context."""
    await channel_layer.group_send(
        f"notifications_{notification.user_id}",
        {
            "type": "notify",
            "id": notification.pk,
            "title": notification.title,
            "message": notification.message,
            "created_at": notification.created_at.strftime("%b %d, %H:%M"),
            "link": link,
        },
    )


def notify_sync(user, title: str, message: str = "", link: str = "") -> None:
    """Create a notification and push via WebSocket. Safe to call from Django views."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    n = create_notification(user, title, message)
    channel_layer = get_channel_layer()
    if channel_layer is not None:
        try:
            async_to_sync(push_ws)(channel_layer, n, link)
        except Exception:
            pass
