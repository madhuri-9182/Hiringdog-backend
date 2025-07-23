import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0131_alter_clientpointofcontact_phone"),
        ("organizations", "0006_alter_organization_slug"),
    ]

    operations = [
        migrations.CreateModel(
            name="JobRole",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("archived", models.BooleanField(default=False)),
                ("name", models.CharField(blank=True, max_length=155)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jobrole",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="job",
            name="job_role",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="jobs",
                to="dashboard.jobrole",
            ),
        ),
    ]
