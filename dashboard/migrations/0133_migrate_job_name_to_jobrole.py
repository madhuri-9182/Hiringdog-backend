from django.db import migrations


def migrate_job_names_to_jobrole(apps, schema_editor):
    Job = apps.get_model("dashboard", "Job")
    JobRole = apps.get_model("dashboard", "JobRole")

    for job in Job.objects.select_related("hiring_manager").all():
        if job.name:
            job_role, _ = JobRole.objects.get_or_create(
                organization=job.hiring_manager.organization, name=job.name
            )
            job.job_role = job_role
            job.save(update_fields=["job_role"])


class Migration(migrations.Migration):

    dependencies = [
        (
            "dashboard",
            "0132_remove_job_name_jobrole_job_role_name",
        ),  # replace with actual previous file
    ]

    operations = [
        migrations.RunPython(migrate_job_names_to_jobrole),
        migrations.RemoveField(
            model_name="job",
            name="name",
        ),
    ]
