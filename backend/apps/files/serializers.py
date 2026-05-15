from rest_framework import serializers

from .models import FileObject


class FileObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileObject
        fields = ["id", "bucket", "path", "public_url", "content_type", "size_bytes", "uploaded_by", "created_at", "deleted_at"]
        read_only_fields = fields
