from django.db import migrations, models


def rename_staff_to_counselor(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role="staff").update(role="counselor")


def rename_counselor_to_staff(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role="counselor").update(role="staff")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_user_avatar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Admin"),
                    ("counselor", "Counselor"),
                    ("editor", "Editor"),
                    ("student", "Student"),
                ],
                db_index=True,
                default="student",
                max_length=20,
            ),
        ),
        migrations.RunPython(rename_staff_to_counselor, rename_counselor_to_staff),
    ]
