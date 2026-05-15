from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0013_student_father_mother_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="father_dob",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="student",
            name="father_company",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="student",
            name="father_position",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="student",
            name="mother_dob",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="student",
            name="mother_company",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="student",
            name="mother_position",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
