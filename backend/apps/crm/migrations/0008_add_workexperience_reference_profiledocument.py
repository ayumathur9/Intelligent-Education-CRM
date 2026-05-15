from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0007_remove_studentschooldocument_created_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkExperience",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("company", models.CharField(max_length=200)),
                ("role", models.CharField(blank=True, max_length=200)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("is_current", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="work_experiences",
                        to="crm.student",
                    ),
                ),
            ],
            options={"ordering": ["order", "start_date"]},
        ),
        migrations.CreateModel(
            name="Reference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("organization", models.CharField(blank=True, max_length=200)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("email", models.EmailField(blank=True)),
                ("relationship", models.CharField(blank=True, max_length=100)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="references",
                        to="crm.student",
                    ),
                ),
            ],
            options={"ordering": ["order"]},
        ),
        migrations.CreateModel(
            name="StudentProfileDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("passport", "Passport / Identity"),
                            ("marksheet_10", "10th Marksheet"),
                            ("marksheet_11", "11th Marksheet"),
                            ("marksheet_12", "12th Marksheet"),
                            ("english_proficiency", "English Proficiency (IELTS/PTE)"),
                            ("gre_gmat_other", "GRE/GMAT/Other"),
                        ],
                        db_index=True,
                        max_length=30,
                    ),
                ),
                ("file_name", models.CharField(max_length=255)),
                ("file_path", models.CharField(max_length=500)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile_documents",
                        to="crm.student",
                    ),
                ),
            ],
            options={"ordering": ["category", "uploaded_at"]},
        ),
        migrations.AddIndex(
            model_name="studentprofiledocument",
            index=models.Index(fields=["student", "category"], name="crm_studentprofiledoc_student_cat_idx"),
        ),
    ]
