# Generated by Django 5.1.2 on 2025-05-23 18:54

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0096_candidatetointerviewerfeedback_is_expired'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='max_exp',
            field=models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(50)]),
        ),
        migrations.AddField(
            model_name='job',
            name='min_exp',
            field=models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(50)]),
        ),
    ]
