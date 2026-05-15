import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0008_add_workexperience_reference_profiledocument"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Fix pre-existing uploaded_at nullability drift on studentschooldocument
        migrations.AlterField(
            model_name="studentschooldocument",
            name="uploaded_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        # Add editor FK to student
        migrations.AddField(
            model_name="student",
            name="editor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="edited_students",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # Add pack_selected to student
        migrations.AddField(
            model_name="student",
            name="pack_selected",
            field=models.CharField(
                blank=True,
                choices=[
                    ("premium_mentorship", "Premium Mentorship"),
                    ("founders_mentorship", "Founder's Mentorship"),
                ],
                default="",
                max_length=30,
            ),
        ),
    ]
