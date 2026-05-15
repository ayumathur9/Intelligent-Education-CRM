from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0009_student_editor_pack_selected"),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentschooldocument",
            name="category",
            field=models.CharField(
                choices=[
                    ("essay", "Essay"),
                    ("lor", "Letter of Recommendation"),
                    ("resume", "Resume / CV"),
                    ("additional_student", "Additional (Student)"),
                    ("additional_counsel", "Additional (Counsellor)"),
                ],
                db_index=True,
                max_length=25,
            ),
        ),
    ]
