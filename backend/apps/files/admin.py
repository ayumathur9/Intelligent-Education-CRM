from django.contrib import admin

from .models import FileObject


@admin.register(FileObject)
class FileObjectAdmin(admin.ModelAdmin):
    list_display = ("id", "bucket", "path", "size_bytes", "created_at")
    search_fields = ("bucket", "path")

