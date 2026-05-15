from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0015_priorityitemdismissal"),
    ]

    operations = [
        # Remove orphaned flat work-experience fields (data lives in WorkExperience model)
        migrations.RemoveField(model_name="student", name="work_company"),
        migrations.RemoveField(model_name="student", name="work_role"),
        migrations.RemoveField(model_name="student", name="work_start"),
        migrations.RemoveField(model_name="student", name="work_end"),
        migrations.RemoveField(model_name="student", name="work_current"),
        # Remove orphaned flat referee fields (data lives in Reference model)
        migrations.RemoveField(model_name="student", name="referee_name"),
        migrations.RemoveField(model_name="student", name="referee_org"),
        migrations.RemoveField(model_name="student", name="referee_phone"),
        migrations.RemoveField(model_name="student", name="referee_email"),
        migrations.RemoveField(model_name="student", name="referee_relationship"),
        # Replace legacy unique_together with a NULL-safe UniqueConstraint so that
        # (student, school, course=NULL) is also treated as unique (PostgreSQL 15+ /
        # Django 5.0 nulls_distinct=False).
        migrations.AlterUniqueTogether(
            name="studentpreference",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="studentpreference",
            constraint=models.UniqueConstraint(
                fields=["student", "school", "course"],
                name="unique_student_school_course",
                nulls_distinct=False,
            ),
        ),
    ]
