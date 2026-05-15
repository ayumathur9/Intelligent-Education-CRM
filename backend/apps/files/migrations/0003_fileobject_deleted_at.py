from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0002_fileobject_uploaded_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="fileobject",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
