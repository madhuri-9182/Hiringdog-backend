import re
import string
import secrets
import logging
from django.conf import settings
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError as vde
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from typing import Dict, List, Any, Tuple


def validate_incoming_data(
    data: Dict[str, any],
    required_keys: List[str],
    allowed_keys: List[str] = [],
    partial: bool = False,
    original_data: Dict[str, any] = {},
    form: bool = False,
) -> Dict[str, List[str]]:

    errors: Dict[str, List[str]] = {}
    if not partial:
        for key in required_keys:
            if key not in data or (form and original_data.get(key) in ("", None)):
                errors.setdefault(key, []).append("This is a required key.")

    for key in data:
        if key not in required_keys + allowed_keys:
            errors.setdefault("unexpected_keys", []).append(key)

    return errors


def set_choice_field_error_messages(serializer_instance, field_choices_mapping):
    """
    Set error messages for choice fields dynamically to avoid computation on class definition.

    Args:
        serializer_instance: The serializer instance
        field_choices_mapping: Dict mapping field names to their choice tuples
                              e.g., {'gender': Model.GENDER_CHOICES, 'status': Model.STATUS_CHOICES}
    """
    for field_name, choices in field_choices_mapping.items():
        if field_name in serializer_instance.fields:
            valid_choices = ", ".join([f"{key}({value})" for key, value in choices])
            serializer_instance.fields[field_name].error_messages[
                "invalid_choice"
            ] = f"This is an invalid choice. Valid choices are {valid_choices}"


def get_display_name(name: str, choices: Tuple[Tuple[str, str], ...]):
    role_dict = dict(choices)
    return role_dict.get(name, name)


def get_random_password(length: int = 10) -> str:
    characters = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(characters) for _ in range(length))


def is_valid_gstin(value: str | None, exact_check: bool = True) -> bool:
    if exact_check:
        if not re.fullmatch(settings.REGEX_GSTIN, value.strip()):
            return False
    else:
        if not re.fullmatch(settings.REGEX_GSTIN_BASIC, value.strip()):
            return False
    return True


def is_valid_pan(
    value: str,
    exact_check: bool = True,
) -> bool:
    if exact_check:
        valid = re.search(settings.REGEX_PAN, value)
        if valid:
            return True
    else:
        valid = re.search(settings.REGEX_PAN_BASIC, value)
        if valid:
            return True
    return False


def get_boolean(data: dict, key: str) -> bool:
    return True if str(data.get(key)).lower() == "true" else False


def check_for_email_uniqueness(email: str, user) -> Dict[str, List[str]]:
    errors = {}

    if email:
        try:
            EmailValidator()(email)
        except vde as e:
            errors.setdefault("email", []).extend(e.messages)
        else:
            if email and user.objects.filter(email=email).exists():
                errors.setdefault("email", []).append("This email is already used.")

    return errors


def validate_attachment(
    field_name: str,
    file,
    allowed_extensions: List[str],
    max_size_mb: int,
) -> Dict[str, List[str]]:
    errors = {}

    if file.size > max_size_mb * 1024 * 1024:
        errors.setdefault(field_name, []).append(
            f"File size must be less than or equal to {max_size_mb}MB"
        )

    file_extension = file.name.split(".")[-1].lower()
    if file_extension not in allowed_extensions:
        errors.setdefault(field_name, []).append(
            f"File type must be one of {', '.join(allowed_extensions)}"
        )

    return errors


def validate_json(
    json_data: Dict[str, Any], field_name: str, schema: Dict[str, Any]
) -> Dict[str, List[str]]:
    errors: Dict[str, List[str]] = {}

    try:
        validate(instance=json_data, schema=schema)
    except ValidationError as e:
        errors.setdefault(field_name, []).append(f"Invalid JSON: {str(e)}")
    return errors


def create_or_update_interviewer_prices():
    from dashboard.models import InterviewerPricing

    prices = (
        ("0-4", 1400),
        ("4-7", 1800),
        ("7-10", 2200),
        ("10+", 2500),
    )

    existing_pricings = set(
        InterviewerPricing.objects.values_list("experience_level", flat=True)
    )
    print("Existing pricings:", existing_pricings)

    for year, rate in prices:
        obj, created = InterviewerPricing.objects.update_or_create(
            experience_level=year,
            defaults={"price": rate},
        )
        print(f"Created: {created}, {obj}")

    for pricing in InterviewerPricing.objects.all():
        if pricing.experience_level not in dict(prices):
            pricing.delete()
            print(f"Deleted: {pricing}")


def add_domain_designation():
    from dashboard.models import DesignationDomain

    existing_domains = set(DesignationDomain.objects.values_list("name", flat=True))
    predefined_domains = [
        ("RS_II", "Research Scientist II"),
    ]
    for domain, _ in predefined_domains:
        if domain not in existing_domains:
            DesignationDomain.objects.create(name=domain)


def add_scheduled_time_in_candidate_model():
    from django.db.models import OuterRef, Subquery
    from dashboard.models import Interview, Candidate

    latest_interview_time = (
        Interview.objects.filter(candidate=OuterRef("pk"))
        .order_by("-scheduled_time")
        .values("scheduled_time")[:1]
    )
    Candidate.objects.update(scheduled_time=Subquery(latest_interview_time))


def log_action(message, request=None, level=logging.INFO, logger_name="hdip", **kwargs):
    logger = logging.getLogger(logger_name)

    extra_data = {
        "user_id": getattr(request.user, "id", None) if request else None,
        "path": request.path if request else None,
        "method": request.method if request else None,
        **kwargs,
    }

    log_methods = {
        logging.DEBUG: logger.debug,
        logging.INFO: logger.info,
        logging.WARNING: logger.warning,
        logging.ERROR: logger.error,
        logging.CRITICAL: logger.critical,
    }

    log_method = log_methods.get(level, logger.debug)
    log_method(message, extra=extra_data)


def populate_credit_packages():
    from dashboard.Models.Finance import CreditPackage, CreditPackagePricing

    data = [
        # trial
        {
            "package": "free",
            "pricing": [
                {
                    "country": "IN",
                    "currency": "INR",
                    "price": 7500,
                    "credits": 300,
                    "validity_days": 15,
                },
                {
                    "country": "US",
                    "currency": "USD",
                    "price": 300,
                    "credits": 300,
                    "validity_days": 15,
                },
            ],
        },
        # Basic Plans
        {
            "package": "basic",
            "pricing": [
                {
                    "country": "IN",
                    "currency": "INR",
                    "price": 25000,
                    "credits": 1000,
                    "validity_days": 90,
                },
                {
                    "country": "US",
                    "currency": "USD",
                    "price": 3000,
                    "credits": 3000,
                    "validity_days": 90,
                },
            ],
        },
        # Standard Plans
        {
            "package": "standard",
            "pricing": [
                {
                    "country": "IN",
                    "currency": "INR",
                    "price": 50000,
                    "credits": 2100,
                    "extra_credits": 100,
                    "validity_days": 180,
                },
                {
                    "country": "US",
                    "currency": "USD",
                    "price": 10000,
                    "credits": 10500,
                    "extra_credits": 500,
                    "validity_days": 180,
                },
            ],
        },
        # Premium Plans
        {
            "package": "premium",
            "pricing": [
                {
                    "country": "IN",
                    "currency": "INR",
                    "price": 100000,
                    "credits": 4200,
                    "extra_credits": 200,
                    "validity_days": 365,
                },
                {
                    "country": "US",
                    "currency": "USD",
                    "price": 20000,
                    "credits": 21000,
                    "extra_credits": 1000,
                    "validity_days": 365,
                },
            ],
        },
        # Enterprise (Handled manually or via sales contact)
        {"package": "enterprise", "pricing": []},
    ]

    for item in data:
        package_obj, _ = CreditPackage.objects.get_or_create(name=item["package"])
        for pricing in item["pricing"]:
            CreditPackagePricing.objects.get_or_create(
                package=package_obj,
                country=pricing["country"],
                currency=pricing.get("currency", "INR"),
                defaults={
                    "price": pricing.get("price", 0),
                    "credits": pricing.get("credits", 0),
                    "extra_credits": pricing.get("extra_credits", 0),
                    "validity_days": pricing.get("validity_days", 0),
                    "is_active": True,
                },
            )


def populate_default_credits_to_all_existing_client():
    from dashboard.models import ClientCreditWallet
    from organizations.models import Organization

    default_wallets = []
    for org in Organization.objects.all():
        if not hasattr(org, "wallet"):
            default_wallets.append(ClientCreditWallet(client=org, total_credits=300))
    ClientCreditWallet.objects.bulk_create(default_wallets)
