from django.conf import settings
from django.db import models

from apps.crm.models import Student


class ChatMessage(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="chat_messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender.full_name}: {self.content[:40]}"


class DirectMessage(models.Model):
    """Counselor-to-counselor direct messages. Room = dm_{min_pk}_{max_pk}."""
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_dms")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_dms")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    @staticmethod
    def room_name(user_pk_a: int, user_pk_b: int) -> str:
        lo, hi = sorted([user_pk_a, user_pk_b])
        return f"dm_{lo}_{hi}"

    def __str__(self):
        return f"{self.sender.full_name} → {self.recipient.full_name}: {self.content[:40]}"
