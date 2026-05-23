import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from apps.common.ws_security import WebSocketSecurityMixin


class ChatConsumer(WebSocketSecurityMixin, AsyncWebsocketConsumer):
    async def connect(self):
        self.student_id = self.scope["url_route"]["kwargs"]["student_id"]
        self.room_group_name = f"chat_{self.student_id}"

        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return

        if not await self._is_authorized(user):
            await self.close()
            return

        self.ws_user_id = user.pk  # required by WebSocketSecurityMixin
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self._increment_connection_count(user.pk)

        if user.role == "student":
            await self._mark_messages_read()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        if self.ws_user_id is not None:
            await self._decrement_connection_count(self.ws_user_id)

    async def receive(self, text_data=None, bytes_data=None):
        # Security check (rate limit + ping/pong) — drop if rate exceeded.
        if self.ws_user_id and not await self._check_message_rate(self.ws_user_id):
            await self.send(text_data=json.dumps({
                "type": "error", "code": "rate_limited",
                "message": "Too many messages. Please slow down.",
            }))
            return

        if not text_data:
            return

        # Handle heartbeat pong silently.
        try:
            parsed = json.loads(text_data)
            if parsed.get("type") == "pong":
                return
        except (json.JSONDecodeError, TypeError):
            return

        content = parsed.get("message", "").strip()
        if not content:
            return

        user = self.scope["user"]
        msg = await self._save_message(user, content)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message_id": msg.pk,
                "content": content,
                "sender_id": user.pk,
                "sender_name": user.full_name or user.email,
                "sender_role": user.role,
                "created_at": msg.created_at.strftime("%b %d, %H:%M"),
            },
        )

        notifs = await self._create_chat_notifications(user, content)
        for n in notifs:
            await self.channel_layer.group_send(
                f"notifications_{n['user_pk']}",
                {"type": "notify", "id": n["id"], "title": n["title"],
                 "message": n["message"], "created_at": n["created_at"], "link": n["link"]},
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @sync_to_async
    def _is_authorized(self, user):
        from apps.crm.models import Student

        if user.role == "admin":
            return True
        try:
            student = Student.objects.select_related("counselor", "poc").get(pk=self.student_id)
        except Student.DoesNotExist:
            return False
        if user.role == "student":
            return hasattr(student, "user") and student.user_id == user.pk
        return user.pk in (
            student.counselor_id if student.counselor_id else None,
            student.poc_id if student.poc_id else None,
        )

    @sync_to_async
    def _save_message(self, user, content):
        from apps.chat.models import ChatMessage
        from apps.crm.models import Student

        student = Student.objects.get(pk=self.student_id)
        return ChatMessage.objects.create(student=student, sender=user, content=content)

    @sync_to_async
    def _mark_messages_read(self):
        from apps.chat.models import ChatMessage

        ChatMessage.objects.filter(student_id=self.student_id, is_read=False).exclude(
            sender__role="student"
        ).update(is_read=True)

    @sync_to_async
    def _create_chat_notifications(self, sender, content):
        from apps.crm.models import Student
        from apps.notifications.service import create_notification

        try:
            student = Student.objects.select_related("counselor", "poc").get(pk=self.student_id)
        except Student.DoesNotExist:
            return []

        recipients = []
        sender_name = sender.full_name or sender.email

        if sender.role == "student":
            for counselor in [student.counselor, student.poc]:
                if counselor and counselor.pk != sender.pk:
                    recipients.append((counselor, f"/counselor-interaction-log/?t=student&id={self.student_id}"))
        else:
            if student.user_id and student.user_id != sender.pk:
                recipients.append((student.user, "/interaction-log/"))

        results = []
        for user, link in recipients:
            n = create_notification(
                user,
                title=f"New message from {sender_name}",
                message=content[:120],
            )
            results.append({
                "user_pk": user.pk,
                "id": n.pk,
                "title": n.title,
                "message": n.message,
                "created_at": n.created_at.strftime("%b %d, %H:%M"),
                "link": link,
            })
        return results


class DMConsumer(WebSocketSecurityMixin, AsyncWebsocketConsumer):
    """Direct messages between counselors."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        if user.role not in ("admin", "counselor"):
            await self.close()
            return

        self.ws_user_id = user.pk
        self.other_user_id = int(self.scope["url_route"]["kwargs"]["other_user_id"])
        from apps.chat.models import DirectMessage
        self.room_group_name = DirectMessage.room_name(user.pk, self.other_user_id)

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self._increment_connection_count(user.pk)
        await self._mark_read()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
        if self.ws_user_id is not None:
            await self._decrement_connection_count(self.ws_user_id)

    async def receive(self, text_data=None, bytes_data=None):
        if self.ws_user_id and not await self._check_message_rate(self.ws_user_id):
            await self.send(text_data=json.dumps({
                "type": "error", "code": "rate_limited",
                "message": "Too many messages. Please slow down.",
            }))
            return

        if not text_data:
            return

        try:
            data = json.loads(text_data)
            if data.get("type") == "pong":
                return
        except (json.JSONDecodeError, TypeError):
            return

        content = data.get("message", "").strip()
        if not content:
            return

        user = self.scope["user"]
        msg = await self._save_message(user, content)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "content": content,
                "sender_id": user.pk,
                "sender_name": user.full_name or user.email,
                "created_at": msg.created_at.strftime("%b %d, %H:%M"),
            },
        )

        notif = await self._create_dm_notification(user, content)
        if notif:
            await self.channel_layer.group_send(
                f"notifications_{notif['user_pk']}",
                {"type": "notify", "id": notif["id"], "title": notif["title"],
                 "message": notif["message"], "created_at": notif["created_at"], "link": notif["link"]},
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    @sync_to_async
    def _save_message(self, user, content):
        from apps.chat.models import DirectMessage
        return DirectMessage.objects.create(
            sender=user, recipient_id=self.other_user_id, content=content
        )

    @sync_to_async
    def _mark_read(self):
        from apps.chat.models import DirectMessage
        user = self.scope["user"]
        DirectMessage.objects.filter(
            recipient=user, sender_id=self.other_user_id, is_read=False
        ).update(is_read=True)

    @sync_to_async
    def _create_dm_notification(self, sender, content):
        from apps.notifications.service import create_notification
        from apps.users.models import User

        try:
            recipient = User.objects.get(pk=self.other_user_id)
        except User.DoesNotExist:
            return None

        sender_name = sender.full_name or sender.email
        n = create_notification(
            recipient,
            title=f"New message from {sender_name}",
            message=content[:120],
        )
        return {
            "user_pk": recipient.pk,
            "id": n.pk,
            "title": n.title,
            "message": n.message,
            "created_at": n.created_at.strftime("%b %d, %H:%M"),
            "link": f"/counselor-interaction-log/?t=dm&id={sender.pk}",
        }
