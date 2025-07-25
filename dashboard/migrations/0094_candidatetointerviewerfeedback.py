# Generated by Django 5.1.2 on 2025-05-22 16:14

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0093_alter_candidate_reason_for_dropping_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CandidateToInterviewerFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('archived', models.BooleanField(default=False)),
                ('rating', models.PositiveSmallIntegerField(blank=True, choices=[(5, 'EXTREMELY SATISFIED'), (4, 'SATISFIED'), (3, 'NEUTRAL'), (2, 'NOT SATISFIED'), (1, 'EXTREMELY NOT SATISFIED')], null=True)),
                ('comments', models.TextField(blank=True, null=True)),
                ('interview', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidate_interviewer_feeddback', to='dashboard.interview')),
                ('interviewer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='candidate_interviewer_feedback', to='dashboard.internalinterviewer')),
            ],
            options={
                'unique_together': {('interview', 'interviewer')},
            },
        ),
    ]
