from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0006_refactor_studentschooldocument"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="studentschooldocument",
            name="created_at",
        ),
    ]
