"""
MED-3: Add db_index to Student.email for faster lookup in auto-link and dedup queries.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0019_encrypt_pii_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="email",
            field=models.EmailField(blank=True, db_index=True),
        ),
    ]
