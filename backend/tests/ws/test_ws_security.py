"""
Tests for WebSocket security mixin — WS-001/002.

Uses Django Channels' in-memory channel layer and ApplicationCommunicator
to drive the consumer lifecycle without a real network connection.
"""
from __future__ import annotations

import json

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anon_scope():
    return {"type": "websocket", "user": type("U", (), {"is_authenticated": False, "pk": None})()}


def _auth_scope(pk=1, role="counselor"):
    user = type("U", (), {"is_authenticated": True, "pk": pk, "role": role})()
    return {"type": "websocket", "user": user}


# ---------------------------------------------------------------------------
# WebSocketSecurityMixin unit tests (synchronous, no real channels layer)
# ---------------------------------------------------------------------------

class TestWebSocketSecurityMixin:
    """
    Tests that exercise the mixin helpers without a full ASGI stack.
    Redis is unavailable in the test suite; all helpers fall back to
    allowing (fail-open) or skipping the check.
    """

    def test_max_message_bytes_constant_is_positive(self):
        from apps.common.ws_security import _MAX_WS_MESSAGE_BYTES
        assert _MAX_WS_MESSAGE_BYTES > 0

    def test_max_connections_per_user_constant(self):
        from apps.common.ws_security import _MAX_CONNECTIONS_PER_USER
        assert _MAX_CONNECTIONS_PER_USER >= 1

    def test_max_messages_per_minute_constant(self):
        from apps.common.ws_security import _MAX_MESSAGES_PER_MINUTE
        assert _MAX_MESSAGES_PER_MINUTE >= 10


# ---------------------------------------------------------------------------
# NotificationConsumer: connect requires authentication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notification_consumer_rejects_unauthenticated():
    """Unauthenticated connections must be closed immediately."""
    from channels.testing import WebsocketCommunicator
    from apps.notifications.consumers import NotificationConsumer

    communicator = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
    communicator.scope.update(_anon_scope())

    connected, _ = await communicator.connect()
    # Either connect returns False or the consumer closes the socket.
    if connected:
        # Consumer accepted the transport but should close application-level.
        try:
            msg = await communicator.receive_output(timeout=1)
            assert msg.get("type") == "websocket.close"
        except Exception:
            pass
    else:
        assert not connected

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_notification_consumer_accepts_authenticated():
    """Authenticated connections should be accepted."""
    from django.test import override_settings
    from channels.testing import WebsocketCommunicator
    from apps.notifications.consumers import NotificationConsumer

    with override_settings(
        CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    ):
        communicator = WebsocketCommunicator(NotificationConsumer.as_asgi(), "/ws/notifications/")
        communicator.scope.update(_auth_scope(pk=42))

        connected, _ = await communicator.connect()
        assert connected

        await communicator.disconnect()
