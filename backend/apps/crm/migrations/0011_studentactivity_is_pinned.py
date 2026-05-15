from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0010_add_additional_document_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentactivity',
            name='is_pinned',
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
