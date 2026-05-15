import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def migrate_documents(apps, schema_editor):
    StudentSchoolDocument = apps.get_model("crm", "StudentSchoolDocument")
    mapping = {
        "essay_1": "essay",
        "essay_2": "essay",
        "lor_1": "lor",
        "lor_2": "lor",
        "resume": "resume",
    }
    for doc in StudentSchoolDocument.objects.all():
        old_type = getattr(doc, "document_type", "essay_1")
        doc.category = mapping.get(old_type, "essay")
        if doc.uploaded_at is None:
            doc.uploaded_at = django.utils.timezone.now()
        doc.save(update_fields=["category", "uploaded_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0005_add_school_deadline"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Add new fields (nullable/defaulted so existing rows are valid)
        migrations.AddField(
            model_name="studentschooldocument",
            name="category",
            field=models.CharField(
                choices=[("essay", "Essay"), ("lor", "Letter of Recommendation"), ("resume", "Resume / CV")],
                default="essay",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="studentschooldocument",
            name="uploaded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="uploaded_school_documents",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # 2. Migrate existing data
        migrations.RunPython(migrate_documents, migrations.RunPython.noop),
        # 3. Remove the old unique_together constraint
        migrations.AlterUniqueTogether(
            name="studentschooldocument",
            unique_together=set(),
        ),
        # 4. Remove old fields
        migrations.RemoveField(model_name="studentschooldocument", name="document_type"),
        migrations.RemoveField(model_name="studentschooldocument", name="status"),
        migrations.RemoveField(model_name="studentschooldocument", name="updated_at"),
        # 5. Make file_name / file_url non-blank
        migrations.AlterField(
            model_name="studentschooldocument",
            name="file_name",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="studentschooldocument",
            name="file_url",
            field=models.CharField(max_length=500),
        ),
        # 6. Add db_index to category and update ordering via AlterModelOptions
        migrations.AlterField(
            model_name="studentschooldocument",
            name="category",
            field=models.CharField(
                choices=[("essay", "Essay"), ("lor", "Letter of Recommendation"), ("resume", "Resume / CV")],
                db_index=True,
                max_length=20,
            ),
        ),
        migrations.AlterModelOptions(
            name="studentschooldocument",
            options={"ordering": ["category", "uploaded_at"]},
        ),
        migrations.AlterIndexTogether(
            name="studentschooldocument",
            index_together=set(),
        ),
        migrations.AddIndex(
            model_name="studentschooldocument",
            index=models.Index(fields=["student", "school", "category"], name="crm_studen_student_school_cat_idx"),
        ),
    ]
