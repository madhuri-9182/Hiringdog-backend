# Generated by Django 5.1.2 on 2025-07-07 04:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0120_alter_job_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='internalclient',
            name='code',
            field=models.CharField(default='INR', help_text='Country code', max_length=15),
        ),
    ]
