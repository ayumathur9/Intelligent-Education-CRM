"""
HIGH-2: Add is_email_verified flag to User model.
Existing users are marked as verified (backfill True) so staff accounts
are not locked out on upgrade.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_rename_staff_role_to_counselor"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_email_verified",
            field=models.BooleanField(default=False),
        ),
        # Backfill: treat all existing users as verified to avoid lockout on upgrade.
        migrations.RunSQL(
            sql="UPDATE users_user SET is_email_verified = TRUE;",
            reverse_sql="UPDATE users_user SET is_email_verified = FALSE;",
        ),
    ]
