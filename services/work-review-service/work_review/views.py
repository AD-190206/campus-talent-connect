import uuid
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.db import IntegrityError, models, transaction
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .exceptions import ServiceUnavailable
from .models import Deliverable, Review
from .serializers import DeliverableSerializer, ReviewSerializer
from .project_client import (
    complete_project,
    get_project,
    ProjectNotFoundError,
    ProjectAuthorizationError,
    ProjectServiceUnavailableError,
)
from .assignment_client import (
    complete_assignment,
    get_assignment,
    AssignmentNotFoundError,
    AssignmentAuthorizationError,
    AssignmentServiceUnavailableError,
)

from .payment_client import (
    find_assignment_payment,
    post_payment_request,
    process_payment_request,
    release_payment_request,
    PaymentServiceAuthorizationError,
    PaymentServiceUnavailableError,
)


def envelope(data, message, http_status=status.HTTP_200_OK):
    return Response({"data": data, "message": message}, status=http_status)


def uuid_query_param(request, name):
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise ValidationError({name: "Must be a valid UUID."})


def fetch_assignment(assignment_id, request):
    """Fetch an assignment, translating client errors into API errors."""
    try:
        return get_assignment(
            assignment_id=assignment_id,
            access_token=request.auth,
        )
    except AssignmentNotFoundError:
        raise NotFound("Assignment not found.")
    except AssignmentAuthorizationError:
        raise PermissionDenied("Assignment access was denied.")
    except AssignmentServiceUnavailableError:
        raise ServiceUnavailable(
            "Assignment Service is temporarily unavailable."
        )


def require_assignment_client(assignment_id, request):
    """The caller must be the client recorded on the assignment."""
    assignment = fetch_assignment(assignment_id, request)

    if str(assignment.get("client_id")) != str(request.user.user_id):
        raise PermissionDenied(
            "You are not the client for this assignment."
        )

    return assignment


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return envelope(
            {"service": "work-review-service", "status": "healthy"},
            "Health check successful",
        )


class WorkListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DeliverableSerializer

    def get_queryset(self):
        """
        STUDENT: own deliverables.
        CLIENT:  deliverables of one assignment they own (assignment_id required).
        ADMIN:   everything.
        Optional filters: assignment_id, status.
        """
        user = self.request.user
        assignment_id = uuid_query_param(self.request, "assignment_id")

        if user.role == "STUDENT":
            queryset = Deliverable.objects.filter(student_id=user.user_id)
        elif user.role == "ADMIN":
            queryset = Deliverable.objects.all()
        elif user.role == "CLIENT":
            if not assignment_id:
                raise ValidationError(
                    {"assignment_id": "This parameter is required for clients."}
                )
            require_assignment_client(assignment_id, self.request)
            queryset = Deliverable.objects.all()
        else:
            queryset = Deliverable.objects.none()

        if assignment_id:
            queryset = queryset.filter(assignment_id=assignment_id)

        work_status = self.request.query_params.get("status")
        if work_status:
            queryset = queryset.filter(status=work_status)

        return queryset

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return envelope(
            response.data,
            "Work created successfully.",
            status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        user = self.request.user

        if user.role != "STUDENT":
            raise PermissionDenied(
                "Only students can create work submissions."
            )

        assignment_id = serializer.validated_data["assignment_id"]
        assignment = fetch_assignment(assignment_id, self.request)

        assigned_student_id = assignment.get("student_id")

        if str(assigned_student_id) != str(user.user_id):
            raise PermissionDenied(
                "You are not the student assigned to this assignment."
            )

        if assignment.get("status", "active") != "active":
            raise ValidationError(
                {"assignment_id": "Work can only be added to an active assignment."}
            )

        serializer.save(
            student_id=user.user_id,
            project_id=assignment["project_id"],
        )


class WorkDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DeliverableSerializer
    lookup_field = "id"
    lookup_url_kwarg = "work_id"

    def get_queryset(self):
        user = self.request.user

        if user.role == "STUDENT":
            return Deliverable.objects.filter(student_id=user.user_id)

        # Clients are checked against the assignment in get_object().
        if user.role in {"ADMIN", "CLIENT"}:
            return Deliverable.objects.all()

        return Deliverable.objects.none()

    def get_object(self):
        work = super().get_object()

        if self.request.user.role == "CLIENT":
            require_assignment_client(work.assignment_id, self.request)

        return work

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return envelope(response.data, "Work retrieved successfully.")

    def update(self, request, *args, **kwargs):
        if request.user.role != "STUDENT":
            raise PermissionDenied("Only the assigned student can edit work.")

        response = super().update(request, *args, **kwargs)
        return envelope(response.data, "Work updated successfully.")


class SubmitWorkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, work_id):
        try:
            work = Deliverable.objects.get(id=work_id)
        except Deliverable.DoesNotExist:
            raise NotFound("Work record not found.")

        if (request.user.role != "STUDENT" or str(work.student_id) != str(request.user.user_id)):
            raise PermissionDenied("You cannot submit this work record.")

        if work.status not in [
            Deliverable.Status.DRAFT,
            Deliverable.Status.REVISION_REQUESTED,
        ]:
            return Response(
                {
                    "error": "Only draft work or work requiring revisions can be submitted.",
                    "code": "INVALID_STATE_TRANSITION",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not work.submission_url:
            return Response(
                {
                    "error": "Provide a submission URL before submitting work.",
                    "code": "SUBMISSION_URL_REQUIRED",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        work.status = Deliverable.Status.SUBMITTED
        work.submitted_at = timezone.now()
        work.save(update_fields=["status", "submitted_at", "updated_at"])

        return envelope(
            DeliverableSerializer(work).data,
            "Work submitted successfully.",
        )


def verify_client_ownership(work, request):
    """Verify that the authenticated client owns this work's project."""
    access_token = request.auth

    try:
        assignment = get_assignment(
            assignment_id=work.assignment_id,
            access_token=access_token,
        )

        # Ensure the assignment's project agrees with the local work record.
        assignment_project_id = assignment.get("project_id")
        if str(assignment_project_id) != str(work.project_id):
            raise PermissionDenied(
                "The work record does not match its assignment."
            )

        project = get_project(
            project_id=work.project_id,
            access_token=access_token,
        )

    except (AssignmentNotFoundError, ProjectNotFoundError):
        raise NotFound("The assignment or project was not found.")
    except (AssignmentAuthorizationError, ProjectAuthorizationError):
        raise PermissionDenied(
            "Ownership verification was denied by a required service."
        )
    except (
        AssignmentServiceUnavailableError,
        ProjectServiceUnavailableError,
    ):
        raise ServiceUnavailable(
            "Ownership verification is temporarily unavailable."
        )

    if str(project.get("client_id")) != str(request.user.user_id):
        raise PermissionDenied(
            "You are not the client who owns this project."
        )

    return assignment, project

def verify_review_eligibility(assignment_id, reviewee_id, request):
    """Verify that the reviewer and reviewee are participants in the assignment."""
    user = request.user
    access_token = request.auth

    try:
        assignment = get_assignment(
            assignment_id=assignment_id,
            access_token=access_token,
        )

        student_id = assignment.get("student_id")
        project_id = assignment.get("project_id")

        if not student_id or not project_id:
            raise ServiceUnavailable(
                "The assignment service returned incomplete assignment data."
            )

        project = get_project(
            project_id=project_id,
            access_token=access_token,
        )

    except (AssignmentNotFoundError, ProjectNotFoundError):
        raise NotFound("The assignment or project was not found.")
    except (AssignmentAuthorizationError, ProjectAuthorizationError):
        raise PermissionDenied(
            "Review eligibility verification was denied by a required service."
        )
    except (
        AssignmentServiceUnavailableError,
        ProjectServiceUnavailableError,
    ):
        raise ServiceUnavailable(
            "Review eligibility verification is temporarily unavailable."
        )

    project_client_id = project.get("client_id")

    if not project_client_id:
        raise ServiceUnavailable(
            "The project service returned incomplete project data."
        )

    user_id = str(user.user_id)
    student_id = str(student_id)
    client_id = str(project_client_id)
    reviewee_id = str(reviewee_id)

    if user.role == "STUDENT":
        if user_id != student_id:
            raise PermissionDenied(
                "You are not the student assigned to this assignment."
            )
        if reviewee_id != client_id:
            raise ValidationError({
                "reviewee_id": (
                    "Students may review only the client who owns the project."
                )
            })

    elif user.role == "CLIENT":
        if user_id != client_id:
            raise PermissionDenied(
                "You do not own the project associated with this assignment."
            )
        if reviewee_id != student_id:
            raise ValidationError({
                "reviewee_id": (
                    "Clients may review only the student assigned to this assignment."
                )
            })

    # Reviews are given once the work has been approved and the assignment
    # completed (SRS: reviews follow completion).
    if assignment.get("status") != "completed":
        raise ValidationError({
            "assignment_id": (
                "Reviews can only be submitted for a completed assignment."
            )
        })


class RequestRevisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, work_id):
        try:
            work = Deliverable.objects.get(id=work_id)
        except Deliverable.DoesNotExist:
            raise NotFound("Work record not found.")

        if request.user.role != "CLIENT":
            raise PermissionDenied(
                "Only the project client can request revisions."
            )

        verify_client_ownership(work, request)

        if work.status != Deliverable.Status.SUBMITTED:
            raise ValidationError(
                "Only submitted work can be sent back for revisions."
            )

        feedback = request.data.get("feedback")
        if not isinstance(feedback, str) or not feedback.strip():
            raise ValidationError(
                {"feedback": "Feedback is required when requesting revisions."}
            )

        work.status = Deliverable.Status.REVISION_REQUESTED
        work.feedback = feedback.strip()
        work.reviewed_at = timezone.now()
        work.save(
            update_fields=[
                "status",
                "feedback",
                "reviewed_at",
                "updated_at",
            ]
        )

        return envelope(
            DeliverableSerializer(work).data,
            "Revision requested successfully.",
        )


class ApproveWorkView(APIView):
    """
    Approve a deliverable (API contract §9.2).

    1. Verify the caller owns the project/assignment.
    2. Reuse the assignment's existing payment, or create one from the
       project budget with a stable idempotency key.
    3. Process it (mock provider) if still pending, then release it.
    4. Complete the project and the assignment.
    5. Only then mark the work APPROVED.

    Every step is idempotent, so a failed approval can simply be retried.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, work_id):
        try:
            work = Deliverable.objects.get(id=work_id)
        except Deliverable.DoesNotExist:
            raise NotFound("Work record not found.")

        if request.user.role != "CLIENT":
            raise PermissionDenied(
                "Only the project client can approve work."
            )

        assignment, project = verify_client_ownership(work, request)

        if work.status == Deliverable.Status.APPROVED:
            return envelope(
                DeliverableSerializer(work).data,
                "Work has already been approved.",
            )

        if work.status != Deliverable.Status.SUBMITTED:
            raise ValidationError(
                "Only submitted work can be approved."
            )

        # The published project budget is the payment amount source.
        try:
            amount = Decimal(str(project["budget"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ServiceUnavailable(
                "The project service returned an invalid project budget."
            )

        if not amount.is_finite() or amount <= 0:
            raise ValidationError(
                {"budget": "The project budget must be greater than zero."}
            )

        assignment_id = str(work.assignment_id)
        access_token = request.auth

        try:
            payment = find_assignment_payment(assignment_id, access_token)

            if payment is None:
                # A stable key lets a retry reuse the payment request.
                payment = post_payment_request(
                    "api/payments/",
                    {
                        "assignment_id": assignment_id,
                        "payer_id": str(request.user.user_id),
                        "payee_id": str(work.student_id),
                        "amount": str(amount),
                        "idempotency_key": (
                            f"work-review-assignment-{assignment_id}"
                        ),
                    },
                    access_token,
                )["data"]

            payment_id = payment["id"]

            if payment.get("status") in {"PENDING", "PROCESSING"}:
                payment = process_payment_request(
                    payment_id,
                    access_token,
                )["data"]

            if payment.get("status") == "FAILED":
                raise ValidationError(
                    "Payment processing failed; work has not been approved."
                )

            if payment.get("status") == "SUCCESS":
                payment = release_payment_request(
                    payment_id,
                    access_token,
                )["data"]

            if payment.get("status") != "RELEASED":
                raise ServiceUnavailable(
                    "Payment release could not be confirmed; "
                    "work has not been approved."
                )

        except PaymentServiceAuthorizationError:
            raise PermissionDenied(
                "The Payment Service rejected the caller's credentials."
            )
        except PaymentServiceUnavailableError:
            raise ServiceUnavailable(
                "The Payment Service is temporarily unavailable."
            )

        try:
            complete_project(work.project_id, access_token)
            complete_assignment(work.assignment_id, access_token)
        except (ProjectNotFoundError, AssignmentNotFoundError):
            raise NotFound("The assignment or project was not found.")
        except (ProjectAuthorizationError, AssignmentAuthorizationError):
            raise PermissionDenied(
                "Completion was denied by a required service."
            )
        except (
            ProjectServiceUnavailableError,
            AssignmentServiceUnavailableError,
        ):
            raise ServiceUnavailable(
                "Payment was released but completion could not be recorded; "
                "retry the approval."
            )

        # Only mark the work approved after release and completion succeed.
        with transaction.atomic():
            locked_work = Deliverable.objects.select_for_update().get(
                id=work.id
            )

            # Re-check state after acquiring the lock.
            if locked_work.status == Deliverable.Status.APPROVED:
                return envelope(
                    DeliverableSerializer(locked_work).data,
                    "Work has already been approved.",
                )

            if locked_work.status != Deliverable.Status.SUBMITTED:
                raise ValidationError(
                    "Work status changed during approval; refresh and retry."
                )

            locked_work.status = Deliverable.Status.APPROVED
            locked_work.payment_requested = True
            locked_work.reviewed_at = timezone.now()
            locked_work.save(
                update_fields=[
                    "status",
                    "payment_requested",
                    "reviewed_at",
                    "updated_at",
                ]
            )

        return Response({
            "data": {
                **DeliverableSerializer(locked_work).data,
                "payment": {
                    "id": payment["id"],
                    "status": payment.get("status"),
                },
            },
            "message": "Work approved and payment released successfully.",
        })


class ReviewListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        user = self.request.user

        if user.role == "ADMIN":
            queryset = Review.objects.all()
        else:
            queryset = Review.objects.filter(
                models.Q(reviewer_id=user.user_id)
                | models.Q(reviewee_id=user.user_id)
            )

        assignment_id = uuid_query_param(self.request, "assignment_id")
        if assignment_id:
            queryset = queryset.filter(assignment_id=assignment_id)

        return queryset

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return envelope(
            response.data,
            "Review submitted successfully.",
            status.HTTP_201_CREATED,
        )

    def perform_create(self, serializer):
        user = self.request.user

        if user.role not in {"STUDENT", "CLIENT"}:
            raise PermissionDenied(
                "Only students and clients can create reviews."
            )

        assignment_id = serializer.validated_data["assignment_id"]
        reviewee_id = serializer.validated_data["reviewee_id"]

        verify_review_eligibility(
            assignment_id=assignment_id,
            reviewee_id=reviewee_id,
            request=self.request,
        )

        try:
            with transaction.atomic():
                serializer.save(
                    reviewer_id=user.user_id,
                    reviewer_role=user.role,
                )

        except IntegrityError as exc:
            cause = exc.__cause__
            details = str(cause or exc)
            constraint_name = getattr(
                getattr(cause, "diag", None),
                "constraint_name",
                None,
            )

            is_duplicate_review = (
                constraint_name == "unique_review_per_assignment_reviewer"
                or "unique_review_per_assignment_reviewer" in details
                or (
                    "work_review_review.assignment_id" in details
                    and "work_review_review.reviewer_id" in details
                )
            )

            if not is_duplicate_review:
                raise

            raise ValidationError({
                "assignment_id": (
                    "You have already submitted a review "
                    "for this assignment."
                )
            }) from exc


class ReviewDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReviewSerializer
    lookup_field = "id"
    lookup_url_kwarg = "review_id"

    def get_queryset(self):
        user = self.request.user

        if user.role == "ADMIN":
            return Review.objects.all()

        return Review.objects.filter(
            models.Q(reviewer_id=user.user_id)
            | models.Q(reviewee_id=user.user_id)
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return envelope(response.data, "Review retrieved successfully.")
