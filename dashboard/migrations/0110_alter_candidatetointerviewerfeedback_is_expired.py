# Generated by Django 5.1.2 on 2025-06-01 17:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0109_alter_billinglog_reason"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="candidatetointerviewerfeedback",
            name="is_expired",
        ),
        migrations.AddField(
            model_name="candidatetointerviewerfeedback",
            name="is_expired",
            field=models.BooleanField(default=False),
        ),
    ]
