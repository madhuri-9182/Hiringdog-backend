from organizations.models import Organization
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from phonenumber_field.modelfields import PhoneNumberField
from common import constants
from core.models import User
from hiringdogbackend.ModelUtils import SoftDelete, CreateUpdateDateTimeAndArchivedField


class HDIPUsers(CreateUpdateDateTimeAndArchivedField):
    """I just keep this model for future enhancement otherwise I prefer to use userprofile model as HDIP User"""

    objects = SoftDelete()
    object_all = models.Manager()

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="hdipuser", blank=True
    )
    name = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name


class InternalClient(CreateUpdateDateTimeAndArchivedField):
    BILLING_MODE_CHOICES = (("PRE", "Prepaid"), ("POS", "Postpaid"))

    objects = SoftDelete()
    object_all = models.Manager()
    organization = models.OneToOneField(
        Organization,
        related_name="internal_client",
        on_delete=models.CASCADE,
        blank=True,
    )
    name = models.CharField(max_length=255, blank=True)
    brand_name = models.CharField(max_length=255, blank=True)
    website = models.URLField(max_length=255, blank=True)
    domain = models.CharField(max_length=255, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    pan = models.CharField(max_length=10, blank=True)
    is_signed = models.BooleanField(default=False)
    client_level = models.IntegerField(default=0)
    initial_free_interviews_allocation = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0)]
    )
    assigned_to = models.ForeignKey(
        HDIPUsers,
        on_delete=models.SET_NULL,
        related_name="internalclients",
        null=True,
        blank=True,
    )
    address = models.TextField(max_length=255, blank=True)
    code = models.CharField(max_length=15, default="IN", help_text="Country ISO code")
    billing_mode = models.CharField(
        max_length=15, choices=BILLING_MODE_CHOICES, default="PRE"
    )

    def __str__(self):
        return self.name


class ClientPointOfContact(CreateUpdateDateTimeAndArchivedField):
    objects = SoftDelete()
    object_all = models.Manager()

    client = models.ForeignKey(
        InternalClient,
        related_name="points_of_contact",
        on_delete=models.CASCADE,
        blank=True,
    )
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=True, blank=True)
    phone = PhoneNumberField(null=True, blank=True)

    def __str__(self):
        return self.name


class DesignationDomain(CreateUpdateDateTimeAndArchivedField):
    name = models.CharField(max_length=15, blank=True, unique=True)

    def __str__(self) -> str:
        return self.name


class Stream(CreateUpdateDateTimeAndArchivedField):
    name = models.CharField(max_length=155, unique=True)

    def __str__(self) -> str:
        return self.name


class InternalInterviewer(CreateUpdateDateTimeAndArchivedField):
    objects = SoftDelete()
    object_all = models.Manager()

    organization = models.ManyToManyField(
        Organization, related_name="interviewers", blank=True
    )
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="interviewer", blank=True
    )
    stream = models.ManyToManyField(Stream, related_name="interviewers", blank=True)
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=True, blank=True)
    phone_number = PhoneNumberField(region="IN", unique=True, blank=True)
    current_company = models.CharField(max_length=255, blank=True)
    previous_company = models.CharField(max_length=255, blank=True)
    current_designation = models.CharField(max_length=255, blank=True)
    total_experience_years = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1, message="Expereince should be more than 1 year"),
            MaxValueValidator(50, message="Enter a valid Experience"),
        ],
    )
    total_experience_months = models.PositiveSmallIntegerField(default=0)
    interview_experience_years = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1, message="Expereince should be more than 1 year"),
            MaxValueValidator(50, message="Enter a valid Experience"),
        ],
    )
    interview_experience_months = models.PositiveSmallIntegerField(default=0)
    skills = models.JSONField(default=list, blank=True)  # e.g., ["Java", "Python"]
    cv = models.FileField(upload_to="interviewer_cvs", blank=True, null=True)
    interviewer_level = models.IntegerField(default=0)
    account_number = models.CharField(
        max_length=20, help_text="bank a/c number", null=True, blank=True
    )
    ifsc_code = models.CharField(
        max_length=15, help_text="bank ifsc code", null=True, blank=True
    )
    social_links = models.JSONField(
        default=dict,
        blank=True,
        help_text="A dictionary of social media links related to the interviewer.",
    )
    is_bank_account_updated = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.email}) - {self.current_company}, {self.total_experience_years}y exp"

    def save(self, *args, **kwargs):
        if self.name:
            self.user.profile.name = self.name
            self.user.profile.save()
        return super().save(*args, **kwargs)


class Agreement(CreateUpdateDateTimeAndArchivedField):
    objects = SoftDelete()
    object_all = models.Manager()

    YEARS_OF_EXPERIENCE_CHOICES = (
        ("0-4", "0 - 4 Years"),
        ("4-6", "4 - 6 Years"),
        ("6-8", "6 - 8 Years"),
        ("8-10", "8 - 10 Years"),
        ("10+", "10+ Years"),
    )

    organization = models.ForeignKey(
        Organization,
        related_name="agreements",
        blank=True,
        on_delete=models.SET_NULL,
        null=True,
    )

    years_of_experience = models.CharField(
        max_length=50, choices=YEARS_OF_EXPERIENCE_CHOICES, blank=True
    )
    rate = models.DecimalField(max_digits=10, decimal_places=2, blank=True)
    credits = models.PositiveIntegerField(
        help_text="auto populate according to the rate"
    )

    class Meta:
        indexes = [
            models.Index(fields=["organization", "years_of_experience"]),
        ]

    @classmethod
    def calculate_credits(cls, country_code, rate):
        country = constants.COUNTRY_DETAILS.get(country_code, {"currency": "INR"})
        if country["currency"] == "INR":
            return int(rate / 25)
        else:
            return int(rate)

    def save(self, *args, **kwargs):
        self.credits = self.calculate_credits(
            self.organization.internal_client.code, self.rate
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Organization ID - {self.organization_id} - ₹{self.rate}"

    @classmethod
    def get_years_of_experience(cls, year, month):
        if year < 4 or (year == 4 and month == 0):
            return "0-4"
        elif year < 6 or (year == 6 and month == 0):
            return "4-6"
        elif year < 8 or (year == 8 and month == 0):
            return "6-8"
        elif year < 10 or (year == 10 and month == 0):
            return "8-10"
        else:
            return "10+"


class InterviewerPricing(CreateUpdateDateTimeAndArchivedField):
    objects = SoftDelete()
    object_all = models.Manager()

    EXPERIENCE_LEVEL_CHOICES = [
        ("0-4", "0 - 4 Years"),
        ("4-7", "4 - 7 Years"),
        ("7-10", "7 - 10 Years"),
        ("10+", "10+ Years"),
    ]

    experience_level = models.CharField(
        max_length=10, choices=EXPERIENCE_LEVEL_CHOICES, unique=True
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True)

    def __str__(self):
        return f"{self.experience_level} - ₹{self.price}"

    @classmethod
    def get_year_of_experience(cls, year, month):
        if year < 4 or (year == 4 and month == 0):
            return "0-4"
        elif year < 7 or (year == 7 and month == 0):
            return "4-7"
        elif year < 10 or (year == 10 and month == 0):
            return "7-10"
        else:
            return "10+"
