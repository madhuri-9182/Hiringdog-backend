import calendar
import datetime
import logging
from django.db import transaction
from django.db.models import Q
from django.db.utils import IntegrityError
from django.conf import settings
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from ..serializer import (
    InterviewerAvailabilitySerializer,
    InterviewerRequestSerializer,
    InterviewerDashboardSerializer,
    InterviewFeedbackSerializer,
    InterviewerBankAccountSerializer,
)
from ..models import (
    InterviewerAvailability,
    Candidate,
    Interview,
    InterviewFeedback,
    InternalInterviewer,
)
from ..tasks import (
    send_email_to_multiple_recipients,
    generate_interview_feedback_pdf,
)
from core.permissions import (
    IsInterviewer,
    IsClientAdmin,
    IsClientUser,
    IsClientOwner,
    IsAgency,
    HasRole,
)
from core.models import OAuthToken, Role
from externals.google.google_calendar import GoogleCalendar
from externals.google.google_meet import (
    create_meet_and_calendar_invite,
)
from common import constants
from services.credit_deduction import CreditDeductionService
from services.interview_scheduling import InterviewRequestSchedulingService
from hiringdogbackend.utils import get_boolean, log_action, get_display_name


CONTACT_EMAIL = settings.EMAIL_HOST_USER if settings.DEBUG else settings.CONTACT_EMAIL
INTERVIEW_EMAIL = (
    settings.EMAIL_HOST_USER if settings.DEBUG else settings.INTERVIEW_EMAIL
)


@extend_schema(tags=["Interviewer"])
class InterviewerAvailabilityView(APIView, LimitOffsetPagination):
    serializer_class = InterviewerAvailabilitySerializer
    permission_classes = [IsAuthenticated, IsInterviewer]

    def post(self, request):
        sync = get_boolean(request.query_params, "sync")
        serializer = self.serializer_class(
            data=request.data, context={"interviewer_user": request.user.interviewer}
        )

        try:
            oauth_obj = OAuthToken.objects.get(user=request.user)
        except OAuthToken.DoesNotExist:
            oauth_obj = None

        if serializer.is_valid():
            with transaction.atomic():
                try:
                    interviewer = serializer.save(interviewer=request.user.interviewer)

                    if oauth_obj and sync:
                        combine_start_datetime = datetime.datetime.combine(
                            interviewer.date, interviewer.start_time
                        )
                        combine_end_datetime = datetime.datetime.combine(
                            interviewer.date, interviewer.end_time
                        )

                        iso_format_start_time = combine_start_datetime.isoformat()
                        iso_format_end_time = combine_end_datetime.isoformat()

                        recurrence = serializer.validated_data.get("recurrence")
                        calender = GoogleCalendar()
                        event_details = {
                            "summary": "Interview Available Time",
                            # "location": "123 Main St, Virtual",
                            # "description": "Discussing project milestones and deadlines.",
                            "start": {
                                "dateTime": iso_format_start_time,
                                "timeZone": "Asia/Kolkata",
                            },
                            "end": {
                                "dateTime": iso_format_end_time,
                                "timeZone": "Asia/Kolkata",
                            },
                            "reminders": {
                                "useDefault": False,
                                "overrides": [],
                            },
                            # "attendees": [
                            #     {"email": "attendee1@example.com"},
                            #     {"email": "attendee2@example.com"},
                            # ],
                        }
                        if recurrence:
                            event_details["recurrence"] = [
                                calender.generate_rrule_string(recurrence)
                            ]

                        event = calender.create_event(
                            access_token=oauth_obj.access_token,
                            refresh_token=oauth_obj.refresh_token,
                            user=request.user,
                            event_details=event_details,
                        )
                        interviewer.google_calendar_id = event.pop("id", "")
                        interviewer.save()

                except Exception as e:
                    transaction.set_rollback(True)
                    return Response(
                        {
                            "status": "failed",
                            "message": "Something went wrong while creating the event.",
                            "error": str(e),
                        },
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

            return Response(
                {
                    "status": "success",
                    "message": "Interviewer Availability added successfully.",
                    "data": serializer.data,
                    "event_details": event if oauth_obj and sync else None,
                },
                status=status.HTTP_201_CREATED,
            )

        custom_error = serializer.errors.pop("errors", None)
        return Response(
            {
                "status": "failed",
                "message": "Invalid data.",
                "errors": serializer.errors if not custom_error else custom_error,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def get(self, request):
        today_date = datetime.datetime.now().date()
        interviewer_avi_qs = InterviewerAvailability.objects.filter(
            interviewer=request.user.interviewer, date__gte=today_date
        )

        serializer = self.serializer_class(interviewer_avi_qs, many=True)

        return_response = {
            "status": "success",
            "message": "Successfully retrieve the availability.",
            "results": serializer.data,
        }

        return Response(
            return_response,
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["Interviewer"])
class InterviewerRequestView(APIView):
    serializer_class = InterviewerRequestSerializer
    permission_classes = [
        IsAuthenticated,
        IsClientUser | IsClientAdmin | IsClientOwner | IsAgency,
    ]

    def post(self, request):
        try:
            with transaction.atomic():
                serializer = self.serializer_class(
                    data=request.data, context={"request": request}
                )

                if not serializer.is_valid():
                    return self._handle_validation_error(serializer)

                return self._process_interview_request(serializer, request)

        except Exception as e:
            log_action(str(e), request, logging.ERROR)
            return Response(
                {
                    "status": "failed",
                    "message": "An error occurred while processing your request.",
                    "error": str(e) if settings.DEBUG else "Internal server error",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _handle_validation_error(self, serializer):
        """Handle serializer validation errors"""
        custom_error = serializer.errors.pop("errors", None)
        return Response(
            {
                "status": "failed",
                "message": "Invalid data.",
                "errors": serializer.errors if not custom_error else custom_error,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _process_interview_request(self, serializer, request):
        """Process the interview request"""
        validated_data = serializer.validated_data
        candidate = validated_data.pop("candidate_obj")
        candidate_id = validated_data["candidate_id"]
        interviewer_ids = validated_data["interviewer_ids"]

        # Calculate required points
        points = Candidate.required_credits(candidate.year, candidate.month)
        organization = candidate.organization

        # Handle initial scheduling credit deduction
        if candidate.status in ["NSCH", "NJ", "REC", "NREC", "HREC", "SNREC"]:
            description = f"{candidate.name}'s Interview"
            if round_name := getattr(candidate.next_round, "name", None):
                description += f" - {round_name}"
            if candidate.status == "NJ":
                description = f"{candidate.name}'s Interview - Reschedule(No Show)"
            CreditDeductionService.deduct_credits(
                organization,
                points,
                organization.internal_client.code,
                description,
                reference=f"candidate: {candidate.id}",
            )

        # Handle rescheduling scenarios
        if candidate.status in ["CSCH", "NJ"]:
            if candidate.status == "CSCH":
                InterviewRequestSchedulingService.cancel_existing_interview(
                    candidate, points
                )
            candidate.status = "NSCH"

        # Update candidate scheduled time
        self._update_candidate_schedule(candidate, validated_data)

        # Prepare and send interviewer notifications
        contexts = InterviewRequestSchedulingService.prepare_interviewer_contexts(
            validated_data, interviewer_ids, candidate_id, request
        )

        # Log the action
        self._log_interview_request(candidate, validated_data, contexts, request)

        # Send notifications
        send_email_to_multiple_recipients.delay(
            contexts,
            "Interview Opportunity Available - Confirm Your Availability",
            "interviewer_interview_notification.html",
        )

        # Update candidate status
        candidate.last_scheduled_initiate_time = timezone.now()
        candidate.status = "SCH"
        candidate.save()

        return Response(
            {
                "status": "success",
                "message": "Scheduling initiated successfully. Interviewers will be notified shortly.",
            },
            status=status.HTTP_200_OK,
        )

    def _update_candidate_schedule(self, candidate, validated_data):
        """Update candidate's scheduled time"""
        schedule_datetime = datetime.datetime.combine(
            validated_data["date"],
            validated_data["time"],
        )

        if not schedule_datetime.tzinfo:
            candidate.scheduled_time = timezone.make_aware(schedule_datetime)
        else:
            candidate.scheduled_time = schedule_datetime

        candidate.save()

    def _log_interview_request(self, candidate, validated_data, contexts, request):
        """Log the interview request action"""
        log_action(
            "Sending interview requests for candidate {} (ID: {}) at {} "
            "for position {} to the following interviewers:\n{}".format(
                candidate.name,
                candidate.id,
                validated_data["date"].strftime("%d/%m/%Y"),
                get_display_name(candidate.designation.job_role.name, constants.ROLE_CHOICES),
                "\n".join(
                    f"  {index}. {context['name']} ({context['email']})"
                    for index, context in enumerate(contexts, start=1)
                ),
            ),
            request,
        )


@extend_schema(tags=["Interviewer"])
class InterviewerRequestResponseView(APIView):
    serializer_class = None

    def post(self, request, request_id):
        try:
            with transaction.atomic():
                try:
                    decode_data = force_str(urlsafe_base64_decode(request_id))
                    data_parts = decode_data.split(";")
                    if len(data_parts) != 7:
                        raise ValueError("Invalid data format")

                    (
                        interviewer_availability_id,
                        candidate_id,
                        schedule_time,
                        booked_by,
                        expired_time,
                        scheduling_id,
                        action,
                    ) = [item.split(":", 1)[1] for item in data_parts]
                except Exception:
                    return Response(
                        {"status": "failed", "message": "Invalid Request ID format."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                expired_time = datetime.datetime.strptime(
                    expired_time, "%Y-%m-%d %H:%M:%S.%f"
                )
                if datetime.datetime.now() > expired_time:
                    return Response(
                        {"status": "failed", "message": "Request expired"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                interviewer_availability = (
                    InterviewerAvailability.objects.select_for_update()
                    .filter(pk=interviewer_availability_id)
                    .first()
                )
                candidate = (
                    Candidate.objects.select_for_update().select_related("designation__job_role")
                    .filter(pk=candidate_id)
                    .first()
                )

                if candidate.status == "SCH":
                    try:
                        scheduling_attempts = candidate.scheduling_attempts.latest(
                            "created_at"
                        )
                    except ObjectDoesNotExist:
                        scheduling_attempts = None
                    if scheduling_attempts and scheduling_id != str(
                        scheduling_attempts.id
                    ):
                        return Response(
                            {
                                "status": "failed",
                                "message": "This interview schedule has expired or was cancelled.",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                if not interviewer_availability or not candidate:
                    return Response(
                        {
                            "status": "failed",
                            "message": "Invalid Interviewer or Candidate.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if candidate.status == "CSCH":
                    return Response(
                        {
                            "status": "failed",
                            "message": "The candidate is currently occupied and has already been assigned to an interviewer.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if candidate.status not in ["SCH", "NSCH"]:
                    return Response(
                        {"status": "failed", "message": "Invalid request"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                schedule_time = datetime.datetime.strptime(
                    schedule_time, "%Y-%m-%d %H:%M:%S"
                )
                schedule_time = timezone.make_aware(schedule_time)

                # To handle multiple interview requests from different clients to the same interviewer scenario
                schedule_time_after_one_hour = schedule_time + datetime.timedelta(
                    hours=1
                )
                schedule_time_before_one_hour = schedule_time - datetime.timedelta(
                    hours=1
                )
                if (
                    Interview.objects.select_for_update()
                    .filter(
                        interviewer=interviewer_availability.interviewer,
                        status="CSCH",
                    )
                    .filter(
                        Q(scheduled_time=schedule_time)
                        | Q(
                            scheduled_time__gte=schedule_time_before_one_hour,
                            scheduled_time__lt=schedule_time,
                        )
                        | Q(
                            scheduled_time__lte=schedule_time_after_one_hour,
                            scheduled_time__gt=schedule_time,
                        )
                    )
                    .exists()
                ):
                    return Response(
                        {
                            "status": "failed",
                            "message": "There must be a 1-hour gap between two consecutive scheduled interviews.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if (
                    Interview.objects.select_for_update()
                    .filter(
                        interviewer=interviewer_availability.interviewer,
                        scheduled_time=schedule_time,
                        status="CSCH",
                    )
                    .exists()
                ):
                    return Response(
                        {
                            "status": "failed",
                            "message": "Interviewer already has a scheduled interview at this time.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if action == "accept":
                    try:
                        interview_obj = (
                            Interview.objects.select_for_update()
                            .filter(candidate=candidate)
                            .order_by("-id")
                            .first()
                        )

                        interview = Interview.objects.create(
                            candidate=candidate,
                            interviewer=interviewer_availability.interviewer,
                            status="CSCH",
                            scheduled_time=schedule_time,
                            total_score=100,
                            previous_interview=interview_obj,
                            availability=interviewer_availability,
                            job_round=candidate.next_round,
                        )
                    except IntegrityError as e:
                        log_action(
                            f"Integrity error when creating interview: {str(e)}",
                            request,
                            level=logging.ERROR,
                        )
                        return Response(
                            {
                                "status": "failed",
                                "message": "Interviewer already has a scheduled interview at this time.",
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    original_start_time = interviewer_availability.start_time
                    original_end_time = interviewer_availability.end_time

                    # updating with the booked time
                    interviewer_availability.start_time = schedule_time.time()
                    interviewer_availability.end_time = (
                        schedule_time + datetime.timedelta(hours=1)
                    ).time()
                    interviewer_availability.booked_by_id = booked_by
                    interviewer_availability.is_scheduled = True
                    interviewer_availability.save()

                    # Preserve original full datetime range
                    availability_date = interviewer_availability.date

                    original_start_dt = timezone.make_aware(
                        datetime.datetime.combine(
                            availability_date, original_start_time
                        )
                    )

                    original_end_date = (
                        availability_date + datetime.timedelta(days=1)
                        if original_end_time <= original_start_time
                        else availability_date
                    )

                    original_end_dt = timezone.make_aware(
                        datetime.datetime.combine(original_end_date, original_end_time)
                    )

                    # creating new available instance for if interviewer is futher available with 1hour before and after time gap
                    # Scheduled interview time
                    scheduled_start_dt = schedule_time
                    scheduled_end_dt = schedule_time + datetime.timedelta(hours=1)

                    # New available slots with 1-hour gap before and after
                    gap = datetime.timedelta(hours=1)
                    new_slots = []

                    # --- Before slot: from original_start_dt to (scheduled_start - 1 hour)
                    before_slot_end_dt = scheduled_start_dt - gap
                    if (before_slot_end_dt - original_start_dt) >= datetime.timedelta(
                        hours=1
                    ):
                        new_slots.append(
                            InterviewerAvailability(
                                interviewer=interviewer_availability.interviewer,
                                date=original_start_dt.date(),
                                start_time=original_start_dt.time(),
                                end_time=before_slot_end_dt.time(),
                                google_calendar_id=interviewer_availability.google_calendar_id,
                            )
                        )

                    # --- After slot: from (scheduled_end + 1 hour) to original_end_dt
                    after_slot_start_dt = scheduled_end_dt + gap
                    if (original_end_dt - after_slot_start_dt) >= datetime.timedelta(
                        hours=1
                    ):
                        new_slots.append(
                            InterviewerAvailability(
                                interviewer=interviewer_availability.interviewer,
                                date=after_slot_start_dt.date(),
                                start_time=after_slot_start_dt.time(),
                                end_time=original_end_dt.time(),
                                google_calendar_id=interviewer_availability.google_calendar_id,
                            )
                        )

                    # Bulk create available slots
                    InterviewerAvailability.objects.bulk_create(new_slots)

                    # sending the confirmation notification
                    interview_date = schedule_time.strftime("%d/%m/%Y")
                    interview_time = schedule_time.strftime("%I:%M %p")

                    meeting_link, event_id = create_meet_and_calendar_invite(
                        interviewer_availability.interviewer.email,
                        candidate.email,
                        schedule_time,
                        schedule_time + datetime.timedelta(hours=1),
                        candidate_name=candidate.name,
                        designation_name=get_display_name(candidate.designation.job_role.name, constants.ROLE_CHOICES),
                        recruiter_email=candidate.added_by.user.email,
                        round_name=getattr(candidate.next_round, "name", "Round"),
                    )

                    interview.scheduled_service_account_event_id = event_id
                    interview.meeting_link = meeting_link
                    interview.save()

                    internal_user = candidate.organization.internal_client.assigned_to
                    job_description = candidate.designation.job_description_file

                    contexts = [
                        {
                            "name": candidate.name,
                            "position": get_display_name(candidate.designation.job_role.name, constants.ROLE_CHOICES),
                            "company_name": candidate.organization.name,
                            "interview_date": interview_date,
                            "interview_time": interview_time,
                            "interviewer": interviewer_availability.interviewer.name,
                            "email": candidate.email,
                            "template": "interview_confirmation_candidate_notification.html",
                            "recruiter_email": candidate.added_by.user.email,
                            "subject": f"Interview Scheduled - {get_display_name(candidate.designation.job_role.name, constants.ROLE_CHOICES)}",
                            "meeting_link": meeting_link,
                            "from_email": INTERVIEW_EMAIL,
                        },
                        {
                            "name": interviewer_availability.interviewer.name,
                            "position": get_display_name(candidate.designation.job_role.name, constants.ROLE_CHOICES),
                            "interview_date": interview_date,
                            "interview_time": interview_time,
                            "candidate": candidate.name,
                            "email": interviewer_availability.interviewer.email,
                            "template": "interview_confirmation_interviewer_notification.html",
                            "subject": f"Interview Assigned - {candidate.name}",
                            "meeting_link": meeting_link,
                            "from_email": INTERVIEW_EMAIL,
                            "attachments": [
                                {
                                    "filename": job_description.name.split("/")[-1],
                                    "content": job_description.read(),
                                    "content_type": "application/pdf",
                                }
                            ],
                        },
                        {
                            "name": candidate.organization.name,
                            "position": get_display_name(candidate.designation.job_role.name, constants.ROLE_CHOICES),
                            "interview_date": interview_date,
                            "interview_time": interview_time,
                            "candidate": candidate.name,
                            "email": getattr(
                                getattr(candidate.added_by, "user", None),
                                "email",
                                candidate.designation.hiring_manager.user.email,
                            ),
                            "template": "interview_confirmation_client_notification.html",
                            "subject": f"Interview Scheduled - {candidate.name}",
                            "meeting_link": meeting_link,
                            "from_email": INTERVIEW_EMAIL,
                        },
                        {
                            "organization_name": candidate.organization.name,
                            "internal_user_name": internal_user.name,
                            "position": get_display_name(candidate.designation.job_role.name, constants.ROLE_CHOICES),
                            "interview_date": interview_date,
                            "interview_time": interview_time,
                            "candidate_name": candidate.name,
                            "email": internal_user.user.email,
                            "template": "internal_interview_scheduling_confirmation.html",
                            "subject": f"Interview Scheduled - {candidate.name}",
                            "meeting_link": meeting_link,
                            "from_email": INTERVIEW_EMAIL,
                        },
                    ]

                    send_email_to_multiple_recipients.delay(
                        contexts,
                        "",
                        "",
                    )

                    return Response(
                        {"status": "success", "message": "Interview Confirmed"},
                        status=status.HTTP_200_OK,
                    )

                return Response(
                    {"status": "success", "message": "Interview Rejected"},
                    status=status.HTTP_200_OK,
                )
        except Exception as e:
            log_action(f"Error: {str(e)}", request, level=logging.ERROR)
            return Response(
                {
                    "status": "failed",
                    "message": "An unexpected error occurred. Please try again later.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class InterviewerAcceptedInterviewsView(APIView, LimitOffsetPagination):
    serializer_class = InterviewerDashboardSerializer
    permission_classes = (IsAuthenticated, IsInterviewer)

    def get(self, request):
        accepted_interviews_qs = Interview.objects.filter(
            interviewer=request.user.interviewer,
            status="CSCH",
            scheduled_time__gte=timezone.now() - datetime.timedelta(hours=1),
        ).select_related(
            "candidate__next_round",
            "candidate__designation__job_role",
            "candidate__specialization",
        )
        paginated_queryset = self.paginate_queryset(accepted_interviews_qs, request)
        serializer = self.serializer_class(paginated_queryset, many=True)
        paginated_data = self.get_paginated_response(serializer.data)
        return Response(
            {
                "status": "success",
                "message": "Accepted interviews fetched successfully",
                **paginated_data.data,
            },
            status=status.HTTP_200_OK,
        )


class InterviewerPendingFeedbackView(APIView, LimitOffsetPagination):
    serializer_class = InterviewerDashboardSerializer
    permission_classes = (IsAuthenticated, IsInterviewer)

    def get(self, request):
        pending_feedback_qs = Interview.objects.filter(
            interviewer=request.user.interviewer,
            interview_feedback__is_submitted=False,
        ).select_related(
            "candidate__next_round",
            "candidate__designation__job_role",
            "candidate__specialization",
        )

        paginated_queryset = self.paginate_queryset(pending_feedback_qs, request)
        serializer = self.serializer_class(paginated_queryset, many=True)
        paginated_data = self.get_paginated_response(serializer.data)
        return Response(
            {
                "status": "success",
                "message": "Pending feedback fetched successfully",
                **paginated_data.data,
            },
            status=status.HTTP_200_OK,
        )


class InterviewerInterviewHistoryView(APIView, LimitOffsetPagination):
    serializer_class = InterviewerDashboardSerializer
    permission_classes = (IsAuthenticated, IsInterviewer)

    def get(self, request):
        interview_history_qs = Interview.objects.filter(
            interviewer=request.user.interviewer, interview_feedback__is_submitted=True
        ).select_related(
            "candidate__next_round",
            "candidate__designation__job_role",
            "candidate__specialization",
        )

        paginated_queryset = self.paginate_queryset(interview_history_qs, request)
        serializer = self.serializer_class(paginated_queryset, many=True)
        paginated_data = self.get_paginated_response(serializer.data)
        return Response(
            {
                "status": "success",
                "message": "Interview history fetched successfully",
                **paginated_data.data,
            },
            status=status.HTTP_200_OK,
        )


class InterviewFeedbackView(APIView, LimitOffsetPagination):
    serializer_class = InterviewFeedbackSerializer
    permission_classes = (IsAuthenticated, HasRole)
    roles_mapping = {
        "GET": [
            Role.INTERVIEWER,
            Role.CLIENT_ADMIN,
            Role.CLIENT_OWNER,
            Role.CLIENT_USER,
            Role.AGENCY,
        ],
        "PATCH": [Role.INTERVIEWER],
        "POST": [Role.INTERVIEWER],
    }

    def get(self, request, interview_id=None):
        if not interview_id:
            return Response(
                {"status": "failed", "message": "Interview id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        interview_feedback_qs = (
            InterviewFeedback.objects.filter(interview_id=interview_id)
            .select_related(
                "interview",
                "interview__candidate__next_round",
                "interview__candidate__specialization",
                "interview__candidate__designation__job_role",
                "interview__interviewer",
            )
            .order_by("-id")
        )
        if request.user.role != Role.INTERVIEWER and request.method == "GET":
            interview_feedback_qs = interview_feedback_qs.filter(
                interview__candidate__organization=request.user.clientuser.organization
            )
        if not interview_feedback_qs.exists():
            return Response(
                {
                    "status": "failed",
                    "message": "No interview feedback found for current interview id",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.serializer_class(interview_feedback_qs.first())
        return Response(
            {
                "status": "success",
                "message": "Interview feedback fetched successfully",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    # def post(self, request):
    #     serializer = self.serializer_class(data=request.data)
    #     serializer.is_valid(raise_exception=True)
    #     interview_id = serializer.validated_data.get("interview_id")
    #     if interview_id:
    #         if InterviewFeedback.objects.filter(interview_id=interview_id).exists():
    #             return Response(
    #                 {
    #                     "status": "failed",
    #                     "message": "Interview feedback for this interview already exists",
    #                 },
    #                 status=status.HTTP_400_BAD_REQUEST,
    #             )
    #     serializer.save(is_submitted=True)
    #     return Response(
    #         {
    #             "status": "success",
    #             "message": "Interview feedback added successfully.",
    #             "data": serializer.data,
    #         },
    #         status=status.HTTP_201_CREATED,
    #     )

    def patch(self, request, interview_id=None):
        if not interview_id:
            return Response(
                {"status": "failed", "message": "Interview id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        interview_feedback_qs = (
            InterviewFeedback.objects.filter(interview_id=interview_id)
            .select_related(
                "interview",
                "interview__candidate",
                "interview__candidate__designation",
                "interview__interviewer",
            )
            .order_by("-id")
        )
        if not interview_feedback_qs.exists():
            return Response(
                {
                    "status": "failed",
                    "message": "No interview feedback found for current interview id",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        interview_feedback = interview_feedback_qs.first()
        if interview_feedback.is_submitted:
            return Response(
                {
                    "status": "failed",
                    "message": "Invalid request. Feedback is already submitted.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.serializer_class(
            interview_feedback, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        feedback = serializer.save(is_submitted=True, submitted_at=timezone.now())
        if feedback.overall_remark != "NJ":
            generate_interview_feedback_pdf.delay(interview_feedback.interview.id)
        internal_user = (
            interview_feedback.interview.candidate.organization.internal_client.assigned_to
        )
        interviewer_name = interview_feedback.interview.interviewer.name
        candidate_name = interview_feedback.interview.candidate.name
        position = get_display_name(interview_feedback.interview.candidate.designation.job_role.name, constants.ROLE_CHOICES)
        recruiter = interview_feedback.interview.candidate.added_by

        data = f"interview_id:{interview_feedback.interview.pk}"
        feedback_uid = urlsafe_base64_encode(force_bytes(data))

        contexts = [
            {
                "internal_user_name": internal_user.name,
                "from_email": INTERVIEW_EMAIL,
                "email": internal_user.user.email,
                "organization_name": interview_feedback.interview.candidate.organization.name,
                "candidate_name": candidate_name,
                "interviewer_name": interviewer_name,
                "position": position,
                "interview_date": interview_feedback.interview.scheduled_time.strftime(
                    "%d/%m/%Y %H:%M"
                ),
                "subject": f"Feedback Submitted: Insights from {interviewer_name} on {candidate_name}",
                "template": "internal_interview_submitted_feedback_notification.html",
            },
        ]

        if feedback.overall_remark != "NJ":
            contexts.append(
                {
                    "from_email": INTERVIEW_EMAIL,
                    "email": interview_feedback.interview.candidate.email,
                    "candidate_name": candidate_name,
                    "subject": f"{candidate_name}, how was your interview experience with us?",
                    "template": "candidate_feedback.html",
                    "interview_date": interview_feedback.interview.scheduled_time.strftime(
                        "%d/%m/%Y"
                    ),
                    "interview_time": interview_feedback.interview.scheduled_time.strftime(
                        "%I:%M %p"
                    ),
                    "site_domain": settings.SITE_DOMAIN,
                    "feedback_uid": feedback_uid,
                }
            )

        if recruiter:
            contexts.append(
                {
                    "client_name": recruiter.name,
                    "candidate_name": candidate_name,
                    "subject": f"📝 Feedback Alert: SDE1 Interview Feedback for {candidate_name} is Now Available",
                    "interviewer_name": interviewer_name,
                    "from_email": INTERVIEW_EMAIL,
                    "email": recruiter.user.email,
                    "template": "client_interview_feedback_submitted_notification.html",
                }
            )
        send_email_to_multiple_recipients.delay(contexts, "", "")
        return Response(
            {
                "status": "success",
                "message": "Interview feedback updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class InterviewerBankAccountView(APIView):
    serializer_class = InterviewerBankAccountSerializer
    permission_classes = [IsAuthenticated, IsInterviewer]

    def get(self, request):
        try:
            interviewer = InternalInterviewer.objects.get(user=request.user)
        except InternalInterviewer.DoesNotExist:
            return Response(
                {
                    "status": "success",
                    "message": "Profile not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = InterviewerBankAccountSerializer(interviewer)
        return Response(
            {
                "status": "success",
                "message": "Successfully retrieved bank information.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        try:
            interviewer = InternalInterviewer.objects.get(user=request.user)
        except InternalInterviewer.DoesNotExist:
            return Response(
                {
                    "status": "success",
                    "message": "Profile not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = InterviewerBankAccountSerializer(
            interviewer, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save(is_bank_account_updated=True)
            return Response(
                {
                    "status": "success",
                    "message": "Successfully updated bank information.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "status": "failed",
                "message": "Invalid data.",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
