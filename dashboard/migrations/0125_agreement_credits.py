# Generated by Django 5.1.2 on 2025-07-15 10:27

from django.db import migrations, models
from common import constants


def calculate_credit_value(country_code):
    currency_details = constants.COUNTRY_DETAILS.get(country_code, {})
    currency = currency_details.get("currency", "INR")
    if currency == "INR":
        credit_value = 25
    else:
        credit_value = 1
    return credit_value


def set_credit_value(apps, schema_editor):
    Agreement = apps.get_model("dashboard", "Agreement")
    agreements = Agreement.objects.all()
    to_update = []
    for agreement in agreements:
        country_code = agreement.organization.internal_client.code
        credit_value = calculate_credit_value(country_code)
        agreement.credits = agreement.rate / credit_value
        to_update.append(agreement)
    Agreement.objects.bulk_update(to_update, fields=["credits"])


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0124_remove_clientcreditwallet_balance_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="agreement",
            name="credits",
            field=models.PositiveIntegerField(
                default=0, help_text="auto populate according to the rate"
            ),
            preserve_default=False,
        ),
        migrations.RunPython(set_credit_value),
    ]
