from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0016_remove_orphaned_student_fields_fix_preference_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentschooldocument",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="studentprofiledocument",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
