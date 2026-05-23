"""Celery tasks for the notifications app — ASYNC-002."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.notifications.tasks.push_notification",
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
)
def push_notification(self, user_id: int, title: str, message: str = "", link: str = "") -> None:
    """
    Create a notification record and push it over WebSocket, asynchronously.
    Decouples notification dispatch from the request cycle.
    """
    from apps.users.models import User
    from apps.notifications.service import create_notification, push_ws
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    try:
        user = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        logger.warning("push_notification: user %s not found", user_id)
        return

    notification = create_notification(user, title=title, message=message)

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        try:
            async_to_sync(push_ws)(channel_layer, notification, link)
        except Exception as exc:
            logger.warning("push_notification: WebSocket push failed for user %s — %s", user_id, exc)

    logger.info("push_notification sent to user %s: %s", user_id, title)
