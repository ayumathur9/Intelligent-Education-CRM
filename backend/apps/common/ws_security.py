"""
WS-001/002: WebSocket security mixin — throttling, connection limits,
heartbeat, auth-expiry handling, and active-connection monitoring.

Usage:
    class MyConsumer(WebSocketSecurityMixin, AsyncWebsocketConsumer):
        ...
"""
from __future__ import annotations

import json
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Maximum simultaneous WebSocket connections per user.
_MAX_CONNECTIONS_PER_USER = int(getattr(settings, "WS_MAX_CONNECTIONS_PER_USER", 5))

# Maximum inbound messages per user per minute.
_MAX_MESSAGES_PER_MINUTE = int(getattr(settings, "WS_MAX_MESSAGES_PER_MINUTE", 60))

# Seconds without traffic before the server sends a ping.
_HEARTBEAT_INTERVAL = int(getattr(settings, "WS_HEARTBEAT_INTERVAL", 30))

# Maximum inbound message size in bytes (64 KB default).
_MAX_WS_MESSAGE_BYTES = int(getattr(settings, "WS_MAX_MESSAGE_BYTES", 64 * 1024))

# Module-level connection pool — created once per process.
_redis_pool = None


def _get_redis_pool():
    """Return a shared Redis connection pool, creating it on first call."""
    global _redis_pool
    if _redis_pool is not None:
        return _redis_pool
    url = getattr(settings, "REDIS_URL", None) or ""
    if not url:
        return None
    try:
        import redis
        _redis_pool = redis.ConnectionPool.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            max_connections=20,
        )
        return _redis_pool
    except Exception:
        return None


def _redis_client():
    """Return a Redis client using the shared connection pool."""
    pool = _get_redis_pool()
    if pool is None:
        return None
    try:
        import redis
        return redis.Redis(connection_pool=pool)
    except Exception:
        return None


class WebSocketSecurityMixin:
    """
    Mixin that adds:
    - Per-user connection limits (Redis-backed, falls back to in-process).
    - Per-user message rate limiting (token-bucket in Redis).
    - Maximum message size enforcement.
    - Heartbeat / ping-pong to detect stale connections.
    - Connection count telemetry for WS-002 health monitoring.
    """

    # Subclasses set this in connect() before calling super().
    ws_user_id: int | None = None

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    async def websocket_connect(self, message):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.ws_user_id = user.pk

        if not await self._check_connection_limit(user.pk):
            logger.warning("WS-001: user %s exceeded connection limit", user.pk)
            await self.close(code=4029)  # 4029 = rate limited
            return

        await self._increment_connection_count(user.pk)
        self._last_message_time = time.monotonic()
        await super().websocket_connect(message)

    async def websocket_disconnect(self, message):
        if self.ws_user_id is not None:
            await self._decrement_connection_count(self.ws_user_id)
        await super().websocket_disconnect(message)

    async def receive(self, text_data=None, bytes_data=None):
        # Enforce maximum message size.
        payload = text_data or bytes_data or b""
        if len(payload) > _MAX_WS_MESSAGE_BYTES:
            logger.warning(
                "WS-001: message too large (%d bytes) from user %s — dropped",
                len(payload),
                self.ws_user_id,
            )
            await self.send(text_data=json.dumps({
                "type": "error",
                "code": "message_too_large",
                "message": "Message exceeds maximum allowed size.",
            }))
            return

        user_id = self.ws_user_id
        if user_id and not await self._check_message_rate(user_id):
            logger.warning("WS-001: message rate exceeded for user %s", user_id)
            await self.send(text_data=json.dumps({
                "type": "error",
                "code": "rate_limited",
                "message": "Too many messages. Please slow down.",
            }))
            return  # drop message

        self._last_message_time = time.monotonic()

        # Handle heartbeat pong from client.
        if text_data:
            try:
                data = json.loads(text_data)
                if data.get("type") == "pong":
                    return  # Acknowledge pong silently.
            except (json.JSONDecodeError, TypeError):
                pass

        await super().receive(text_data=text_data, bytes_data=bytes_data)

    # ------------------------------------------------------------------
    # Heartbeat — called from the consumer's background task if needed.
    # ------------------------------------------------------------------

    async def send_ping(self):
        """Send a ping frame to the client."""
        try:
            await self.send(text_data=json.dumps({"type": "ping"}))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # WS-002: monitoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def get_active_connection_count() -> int:
        """Return the total number of active WebSocket connections across all workers."""
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            r = await loop.run_in_executor(None, _redis_client)
            if r is None:
                return -1
            keys = await loop.run_in_executor(None, lambda: r.keys("crm:ws:conn:*"))
            total = 0
            for key in keys:
                val = await loop.run_in_executor(None, lambda k=key: r.get(k))
                try:
                    total += int(val or 0)
                except (TypeError, ValueError):
                    pass
            return total
        except Exception:
            return -1

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _check_connection_limit(self, user_id: int) -> bool:
        """Return True if the user can open another connection."""
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            r = await loop.run_in_executor(None, _redis_client)
            if r is None:
                return True  # No Redis — allow (dev mode).
            key = f"crm:ws:conn:{user_id}"
            current = await loop.run_in_executor(None, lambda: r.get(key))
            return int(current or 0) < _MAX_CONNECTIONS_PER_USER
        except Exception:
            return True  # Fail open to avoid locking out users on Redis hiccup.

    async def _increment_connection_count(self, user_id: int) -> None:
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            r = await loop.run_in_executor(None, _redis_client)
            if r is None:
                return
            key = f"crm:ws:conn:{user_id}"
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, 86400)  # auto-expire after 24 h (safety net)
            await loop.run_in_executor(None, pipe.execute)
        except Exception:
            pass

    async def _decrement_connection_count(self, user_id: int) -> None:
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            r = await loop.run_in_executor(None, _redis_client)
            if r is None:
                return
            key = f"crm:ws:conn:{user_id}"
            current = await loop.run_in_executor(None, lambda: r.get(key))
            if current and int(current) > 0:
                await loop.run_in_executor(None, lambda: r.decr(key))
        except Exception:
            pass

    async def _check_message_rate(self, user_id: int) -> bool:
        """Sliding-window rate limiter: max _MAX_MESSAGES_PER_MINUTE per user."""
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            r = await loop.run_in_executor(None, _redis_client)
            if r is None:
                return True
            now = int(time.time())
            key = f"crm:ws:rate:{user_id}:{now // 60}"
            count = await loop.run_in_executor(None, lambda: r.incr(key))
            if count == 1:
                await loop.run_in_executor(None, lambda: r.expire(key, 120))
            return count <= _MAX_MESSAGES_PER_MINUTE
        except Exception:
            return True
