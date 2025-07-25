# Generated by Django 5.1.2 on 2025-07-17 16:10

from django.db import migrations


def populate_credit_package_descriptions(apps, schema_editor):
    CreditPackage = apps.get_model("dashboard", "CreditPackage")
    descriptions = {
        "free": "Perfect for getting started and testing our platform",
        "basic": "Ideal for small teams and growing businesses",
        "standard": "Most popular choice for established businesses",
        "premium": "Ideal for enterprise-level operations",
        "enterprise": "Tailored solutions for large organizations",
    }

    for name, description in descriptions.items():
        try:
            package = CreditPackage.objects.get(name=name)
            package.description = description
            package.save()
        except CreditPackage.DoesNotExist:
            # If the plan doesn't exist, we skip it
            continue


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0126_clientcredittransaction_description_and_more"),
    ]

    operations = [
        migrations.RunPython(populate_credit_package_descriptions),
    ]
