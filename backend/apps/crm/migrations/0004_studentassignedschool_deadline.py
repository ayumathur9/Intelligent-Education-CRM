from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0003_student_country_of_birth_student_curr_city_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentassignedschool",
            name="deadline",
            field=models.DateField(blank=True, null=True),
        ),
    ]
