"""
HIGH-005: Encrypt sensitive PII fields at rest.

Fields migrated to EncryptedCharField / EncryptedEmailField:
  - Student.passport_number
  - Student.father_annual_income
  - Student.mother_annual_income
  - Student.emergency_mobile
  - Student.emergency_email

The underlying DB column type is unchanged (VARCHAR) — the encrypted value is
stored as a base64-encoded ciphertext string.  Existing plaintext values in
development databases are automatically re-stored in encrypted form the next
time a Student record is saved.

Migration is fully reversible: reversing swaps back to plain CharField/EmailField,
which will contain ciphertext strings until the next save (safe for rollback).
"""

from django.db import migrations
import encrypted_model_fields.fields


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0018_softdelete_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="passport_number",
            field=encrypted_model_fields.fields.EncryptedCharField(blank=True, max_length=50),
        ),
        migrations.AlterField(
            model_name="student",
            name="father_annual_income",
            field=encrypted_model_fields.fields.EncryptedCharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="student",
            name="mother_annual_income",
            field=encrypted_model_fields.fields.EncryptedCharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="student",
            name="emergency_mobile",
            field=encrypted_model_fields.fields.EncryptedCharField(blank=True, max_length=32),
        ),
        migrations.AlterField(
            model_name="student",
            name="emergency_email",
            field=encrypted_model_fields.fields.EncryptedEmailField(blank=True),
        ),
    ]
