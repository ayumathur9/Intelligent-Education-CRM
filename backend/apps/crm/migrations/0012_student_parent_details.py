from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0011_studentactivity_is_pinned'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='parent_name',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='student',
            name='parent_email',
            field=models.EmailField(blank=True),
        ),
        migrations.AddField(
            model_name='student',
            name='parent_phone',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='student',
            name='parent_profession',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='student',
            name='parent_education',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='student',
            name='parent_annual_income',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
