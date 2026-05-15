from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0012_student_parent_details'),
    ]

    operations = [
        # Remove old generic parent fields
        migrations.RemoveField(model_name='student', name='parent_name'),
        migrations.RemoveField(model_name='student', name='parent_email'),
        migrations.RemoveField(model_name='student', name='parent_phone'),
        migrations.RemoveField(model_name='student', name='parent_profession'),
        migrations.RemoveField(model_name='student', name='parent_education'),
        migrations.RemoveField(model_name='student', name='parent_annual_income'),

        # Father fields
        migrations.AddField(model_name='student', name='father_name', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='student', name='father_email', field=models.EmailField(blank=True)),
        migrations.AddField(model_name='student', name='father_phone', field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(model_name='student', name='father_profession', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='student', name='father_education', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='student', name='father_annual_income', field=models.CharField(blank=True, max_length=100)),

        # Mother fields
        migrations.AddField(model_name='student', name='mother_name', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='student', name='mother_email', field=models.EmailField(blank=True)),
        migrations.AddField(model_name='student', name='mother_phone', field=models.CharField(blank=True, max_length=32)),
        migrations.AddField(model_name='student', name='mother_profession', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='student', name='mother_education', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='student', name='mother_annual_income', field=models.CharField(blank=True, max_length=100)),
    ]
