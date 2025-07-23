import jwt
import calendar
from datetime import datetime, timedelta
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.db.models import Q, F
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from typing import Optional, Tuple, Dict, Union
from dashboard.models import (
    BillingLog,
    BillingRecord,
    Candidate,
    ClientCreditWallet,
    Interview,
    InterviewerAvailability,
    InterviewScheduleAttempt,
    Job,
    Stream,
)
from dashboard.tasks import send_mail
from .credit_deduction import CreditDeductionService
from externals.google.google_meet import cancel_meet_and_calendar_invite
from common import constants
from hiringdogbackend.utils import get_display_name

INTERVIEW_EMAIL = (
    settings.EMAIL_HOST_USER if settings.DEBUG else settings.INTERVIEW_EMAIL
)


class InterviewRequestSchedulingService:
    """Service class to handle interview scheduling business logic"""

    @staticmethod
    def handle_late_rescheduling(candidate, interview_obj, points):
        """Handle late rescheduling logic and billing"""
        scheduled_time = interview_obj.scheduled_time
        interviewer = interview_obj.interviewer
        organization = candidate.organization

        # Check if rescheduling is within 3 hours
        if scheduled_time - timedelta(hours=3) <= timezone.now():
            # Deduct credits for late rescheduling
            CreditDeductionService.deduct_credits(
                organization,
                points,
                organization.internal_client.code,
                f"{candidate.name}'s Late Rescheduling",
                reference=f"candidate: {candidate.id}",
            )

            # Handle billing
            InterviewRequestSchedulingService._handle_late_reschedule_billing(
                candidate, interviewer, interview_obj
            )

            # Send notifications
            InterviewRequestSchedulingService._send_cancellation_notifications(
                candidate, interviewer, scheduled_time
            )

    @staticmethod
    def _handle_late_reschedule_billing(candidate, interviewer, interview_obj):
        """Handle billing for late rescheduling"""
        interviewer_amount = (
            settings.INTERVIEWER_LATE_RESCHEDULE_CANCEL_AND_NOT_JOINED_AMOUNT
        )
        client_amount = settings.CLIENT_LATE_RESCHEDULE_CANCEL_AND_NOT_JOINED_AMOUNT
        billing_month = timezone.now().replace(day=1).date()

        # Create or get billing log
        billinglog, _ = BillingLog.objects.get_or_create(
            interview=candidate.interviews.order_by("-id").first(),
            reason="late_rescheduled",
            defaults={
                "billing_month": billing_month,
                "client": candidate.organization,
                "interviewer": interviewer,
                "amount_for_client": client_amount,
                "amount_for_interviewer": interviewer_amount,
            },
        )

        if not billinglog.is_billing_calculated:
            InterviewRequestSchedulingService._update_billing_records(
                candidate, interviewer, billing_month, client_amount, interviewer_amount
            )
            billinglog.is_billing_calculated = True
            billinglog.save()

    @staticmethod
    def _update_billing_records(
        candidate, interviewer, billing_month, client_amount, interviewer_amount
    ):
        """Update billing records for client and interviewer"""
        today = timezone.now()
        end_of_month = calendar.monthrange(today.year, today.month)[1]
        due_date = (today.replace(day=end_of_month) + timedelta(days=10)).date()

        # Update Client BillingRecord
        client_record, created = BillingRecord.objects.get_or_create(
            client=candidate.organization.internal_client,
            billing_month=billing_month,
            defaults={
                "record_type": "CLB",
                "amount_due": client_amount,
                "due_date": due_date,
                "status": "PED",
            },
        )
        if not created:
            client_record.amount_due += client_amount
            client_record.save()

        # Update Interviewer BillingRecord
        interviewer_record, created = BillingRecord.objects.get_or_create(
            interviewer=interviewer,
            billing_month=billing_month,
            defaults={
                "record_type": "INP",
                "amount_due": interviewer_amount,
                "due_date": due_date,
                "status": "PED",
            },
        )
        if not created:
            interviewer_record.amount_due += interviewer_amount
            interviewer_record.save()

    @staticmethod
    def _send_cancellation_notifications(candidate, interviewer, scheduled_time):
        """Send cancellation notifications to interviewer and candidate"""
        # Notification to interviewer
        send_mail.delay(
            to=interviewer.email,
            subject=f"Interview with {candidate.name} has been cancelled",
            template="client_interview_cancelled_notification.html",
            candidate_name=candidate.name,
            interviewer_name=interviewer.name,
            interview_date=timezone.localtime(scheduled_time)
            .date()
            .strftime("%d/%m/%Y"),
            interview_time=timezone.localtime(scheduled_time)
            .time()
            .strftime("%I:%M %p"),
        )

        # Notification to candidate
        send_mail.delay(
            to=candidate.email,
            subject=f"{candidate.name}, Your Interview Has Been Cancelled",
            template="client_candidate_cancelled_notification.html",
            candidate_name=candidate.name,
            interview_date=timezone.localtime(scheduled_time)
            .date()
            .strftime("%d/%m/%Y"),
            interview_time=timezone.localtime(scheduled_time)
            .time()
            .strftime("%I:%M %p"),
        )

    @staticmethod
    def cancel_existing_interview(candidate, points):
        """Cancel existing interview if candidate is rescheduling"""
        interview_obj = (
            Interview.objects.select_for_update()
            .filter(candidate=candidate)
            .order_by("-id")
            .first()
        )

        if not interview_obj:
            return

        # Update interview status
        interview_obj.status = "RESCH"

        # Free up availability
        if hasattr(interview_obj, "availability"):
            interview_obj.availability.booked_by = None
            interview_obj.availability.is_scheduled = False
            interview_obj.availability.save()

        interview_obj.save()

        # Cancel meeting and calendar invite
        cancel_meet_and_calendar_invite(
            interview_obj.scheduled_service_account_event_id
        )

        # Handle late rescheduling
        InterviewRequestSchedulingService.handle_late_rescheduling(
            candidate, interview_obj, points
        )

    @staticmethod
    def prepare_interviewer_contexts(
        serializer_data, interviewer_ids, candidate_id, request
    ):
        """Prepare contexts for interviewer notifications"""
        contexts = []
        schedule_datetime = datetime.combine(
            serializer_data["date"],
            serializer_data["time"],
        )

        scheduling_attempt = InterviewScheduleAttempt.objects.create(
            candidate_id=candidate_id
        )

        for interviewer_obj in InterviewerAvailability.objects.filter(
            pk__in=interviewer_ids, booked_by__isnull=True
        ).select_related("interviewer"):

            accept_uid, reject_uid = (
                InterviewRequestSchedulingService._generate_confirmation_links(
                    interviewer_obj,
                    candidate_id,
                    schedule_datetime,
                    request.user.id,
                    scheduling_attempt.id,
                )
            )

            context = {
                "name": interviewer_obj.interviewer.name,
                "email": interviewer_obj.interviewer.email,
                "interview_date": serializer_data["date"],
                "interview_time": serializer_data["time"],
                "position": get_display_name(
                    Candidate.objects.select_related("designation__job_role")
                    .get(id=candidate_id)
                    .designation.job_role.name,
                    constants.ROLE_CHOICES,
                ),
                "site_domain": settings.SITE_DOMAIN,
                "accept_link": f"/confirmation/{accept_uid}/",
                "reject_link": f"/confirmation/{reject_uid}/",
                "from_email": INTERVIEW_EMAIL,
            }
            contexts.append(context)

        return contexts

    @staticmethod
    def _generate_confirmation_links(
        interviewer_obj, candidate_id, schedule_datetime, user_id, scheduling_id
    ):
        """Generate confirmation links for interviewer"""
        base_data = (
            f"interviewer_avialability_id:{interviewer_obj.id};"
            f"candidate_id:{candidate_id};"
            f"schedule_time:{schedule_datetime};"
            f"booked_by:{user_id};"
            f"expired_time:{datetime.now() + timedelta(hours=1)};"
            f"scheduling_id:{scheduling_id}"
        )

        accept_data = base_data + ";action:accept"
        reject_data = base_data + ";action:reject"

        accept_uid = urlsafe_base64_encode(force_bytes(accept_data))
        reject_uid = urlsafe_base64_encode(force_bytes(reject_data))

        return accept_uid, reject_uid


class InterviewAvailablitySchedulingService:
    """
    Service layer for interview scheduling operations.
    Handles both client-side and candidate-side scheduling logic.
    """

    def __init__(self):
        self.required_field_client = [
            "date",
            "designation_id",
            "experience_year",
            "experience_month",
            "specialization_id",
            "company",
        ]

        self.required_fiels_candidate = ["date", "time", "token"]

    def validate_query_params(
        self, query_params: Dict, is_candidate_view: bool = False
    ) -> Optional[Response]:
        """Validate required query parameters based on view type"""

        required_fields = (
            self.required_fiels_candidate
            if is_candidate_view
            else self.required_field_client
        )

        missing_fields = []
        for field in required_fields:
            if field == "time" and is_candidate_view:
                if not query_params.get(field):
                    missing_fields.append(field)
            elif not query_params.get(field):
                missing_fields.append(field)

        if missing_fields:
            return Response(
                {
                    "status": "failed",
                    "message": f"{', '.join(missing_fields)} are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def validate_sufficient_credit(
        self, required_credits: int, organization
    ) -> Optional[Response]:
        """Validate whether sufficient credits are present"""

        try:
            wallet = ClientCreditWallet.objects.get(client=organization)
        except ClientCreditWallet.DoesNotExist:
            return self._error_response("Invalid client")

        if wallet.total_credits < required_credits:
            return self._error_response(
                f"Insufficient credit. You need {required_credits} credits to continue. Please purchase more."
            )
        return None

    def parse_and_validate_datetime(
        self, date_str: str, time_str: str = None
    ) -> Union[Tuple, Response]:
        """Parse and validate date and time parameters"""
        try:
            formatted_date = datetime.strptime(date_str, "%d/%m/%Y").date()
            today = timezone.now().date()

            if formatted_date < today:
                return self._error_response(
                    "Invalid date - cannot schedule in the past"
                )

            formatted_start_time = None
            end_time = None

            if time_str:
                formatted_start_time = datetime.strptime(time_str, "%H:%M").time()

                # Check if time is in the past for today's date
                if formatted_date == today:
                    current_time = timezone.now().time()
                    if formatted_start_time < current_time:
                        return self._error_response(
                            "Invalid time - cannot schedule in the past"
                        )

                # Calculate end time (1 hour later)
                end_time = (
                    datetime.strptime(time_str, "%H:%M") + datetime.timedelta(hours=1)
                ).time()

            return formatted_date, formatted_start_time, end_time

        except ValueError:
            return self._error_response(
                "Invalid date or time format. Use DD/MM/YYYY for date and HH:MM for time"
            )

    def validate_experience(
        self, year_str: str, month_str: str
    ) -> Union[Tuple[int, int], Response]:
        """Validate and convert year and month experience parameters"""
        try:
            year = int(year_str) if year_str is not None else 0
            if year < 0 or year > 50:
                raise ValueError("Experience years must be between 0 and 50.")

            month = int(month_str) if month_str is not None else 0
            if month < 0 or month > 12:
                raise ValueError("Experience months must be between 0 and 12.")

            return year, month
        except ValueError as e:
            return self._error_response(str(e))

    def validate_specialization_id(self, specialization_id: int) -> Response:
        """Check if specialization is valid"""
        try:
            specialization_id = int(specialization_id)
            if not Stream.objects.filter(pk=specialization_id).exists():
                return self._error_response("Invalid specialization_id")
        except ValueError:
            return self._error_response("Specialization_id should be an integer")

    # ============ DATA RETRIEVAL METHODS ============

    def get_job(self, designation_id: str, organization=None) -> Union[Job, Response]:
        """Get and validate job exists"""
        try:
            if organization:
                return Job.objects.get(
                    pk=designation_id,
                    hiring_manager__organization=organization,
                )
            else:
                return Job.objects.get(pk=designation_id)
        except Job.DoesNotExist:
            return self._error_response("Job not found")

    def get_candidate(
        self, candidate_id: str, organization=None
    ) -> Union[Candidate, Response]:
        """Get and validate candidate exists"""
        try:
            if organization:
                return Candidate.objects.get(organization=organization, pk=candidate_id)
            else:
                return Candidate.objects.get(pk=candidate_id)
        except Candidate.DoesNotExist:
            return self._error_response("Candidate not found")

    # ============ BUSINESS LOGIC METHODS ============

    def calculate_required_credits(
        self, experience_year: int, experience_month: int
    ) -> int:
        """Calculate required credits for the interview"""
        return Candidate.required_credits(experience_year, experience_month)

    def build_skills_query(self, skills: list) -> Q:
        """Build Q object for skills filtering"""
        query = Q()
        for skill in skills:
            query |= Q(interviewer__skills__icontains=f'"{skill}"')
        return query

    def get_interviewer_level_range(self, client_level: int) -> list:
        """Get interviewer level range based on client level"""
        return (
            list(range(client_level - 1, client_level + 1))
            if client_level in [2, 3]
            else [client_level]
        )

    def get_excluded_interviewers(self, candidate: Candidate) -> list:
        """Get interviewer IDs that have already completed rounds for this candidate"""
        return list(
            Interview.objects.filter(
                candidate=candidate,
                status__in=["REC", "SNREC", "NREC", "HREC"],
            )
            .values_list("interviewer", flat=True)
            .distinct()
        )

    def get_interviewer_availability(
        self,
        formatted_date,
        specialization_id: int,
        experience_year: int,
        experience_month: int,
        skills: list,
        company: str,
        client_brand_name: str,
        client_level: int,
        formatted_start_time=None,
        end_time=None,
        candidate: Candidate = None,
    ):
        """Get interviewer availability with all filters applied"""

        # Build skills query
        skills_query = self.build_skills_query(skills)

        # Get interviewer level range
        interviewer_level = self.get_interviewer_level_range(client_level)

        # Calculate minimum experience requirement
        candidate_total_months = experience_year * 12 + experience_month
        required_minimum_months = candidate_total_months + 24

        # Build base queryset
        queryset = (
            InterviewerAvailability.objects.select_related("interviewer")
            .annotate(
                interviewer_total_months=F("interviewer__total_experience_years") * 12
                + F("interviewer__total_experience_months")
            )
            .filter(
                date=formatted_date,
                interviewer__stream__id=specialization_id,
                interviewer_total_months__gte=required_minimum_months,
                interviewer__interviewer_level__in=interviewer_level,
                booked_by__isnull=True,
            )
            .distinct()
        )

        # Exclude interviewers who already interviewed this candidate
        if candidate:
            excluded_interviewers = self.get_excluded_interviewers(candidate)
            queryset = queryset.exclude(interviewer__in=excluded_interviewers)

        # Apply time filter if specified
        if formatted_start_time and end_time:
            queryset = queryset.filter(
                start_time__lte=formatted_start_time, end_time__gte=end_time
            )

        # Apply skills and company exclusion filters
        return (
            queryset.filter(skills_query)
            .exclude(
                Q(interviewer__current_company__iexact=company)
                | Q(interviewer__current_company__iexact=client_brand_name)
            )
            .values("id", "date", "start_time", "end_time")
        )

    # ============ UTILITY METHODS ============

    def _error_response(self, message: str) -> Response:
        """Helper method for error responses"""
        return Response(
            {"status": "failed", "message": message},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _success_response(self, message: str, data=None) -> Response:
        """Helper method for success responses"""
        response_data = {"status": "success", "message": message}
        if data is not None:
            response_data["data"] = data
        return Response(response_data, status=status.HTTP_200_OK)


class CandidateInterviewSchedulingService:

    @staticmethod
    def generate_scheduling_token(candidate_id: int, expired_in_days: int = 7):
        payload = {
            "candidate_id": candidate_id,
            "type": "candidate_scheduling",
            "exp": timezone.now() + timedelta(days=expired_in_days),
            "iat": timezone.now(),
        }

        return jwt.encode(payload, settings.SCHEDULING_SECRET_KEY, algorithm="HS256")

    @staticmethod
    def decode_scheduling_token(token: str):

        try:
            payload = jwt.decode(
                token, settings.SCHEDULING_SECRET_KEY, algorithms=["HS256"]
            )

            if payload.get("type") != "candidate_scheduling":
                raise jwt.InvalidTokenError("Invalid token type.")
            return payload
        except jwt.ExpiredSignatureError:
            raise jwt.ExpiredSignatureError("Scheduling link has expired")
        except jwt.InvalidTokenError:
            raise jwt.InvalidTokenError("Invalid scheduling link.")
