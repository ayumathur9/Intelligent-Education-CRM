from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0006_add_staff_invite"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="tutorial_seen",
            field=models.BooleanField(default=False),
        ),
    ]
