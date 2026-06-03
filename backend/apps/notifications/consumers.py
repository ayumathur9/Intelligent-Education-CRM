import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.common.ws_security import WebSocketSecurityMixin


class NotificationConsumer(WebSocketSecurityMixin, AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.ws_user_id = user.pk
        self.group_name = f"notifications_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Run security checks (rate limit, ping/pong handling) first.
        await super().receive(text_data=text_data, bytes_data=bytes_data)

    async def notify(self, event):
        await self.send(text_data=json.dumps(event))
