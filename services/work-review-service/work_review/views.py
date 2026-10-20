from django.utils import timezone
from django.db import IntegrityError, models, transaction
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .exceptions import ServiceUnavailable
from .models import Deliverable, Review
from .serializers import DeliverableSerializer, ReviewSerializer
from .project_client import (
    get_project,
    ProjectNotFoundError,
    ProjectAuthorizationError,
    ProjectServiceUnavailableError,
)
from .assignment_client import (
    get_assignment,
    AssignmentNotFoundError,
    AssignmentAuthorizationError,
    AssignmentServiceUnavailableError,
)

from .payment_client import (
    post_payment_request,
    process_payment_request,
    release_payment_request,
    PaymentServiceAuthorizationError,
    PaymentServiceUnavailableError,
)

class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "service": "work-review-service",
            "status": "running",
        })


class WorkListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DeliverableSerializer

    def get_queryset(self):
        user = self.request.user

        if user.role == "STUDENT":
            return Deliverable.objects.filter(student_id=user.user_id)

        if user.role == "ADMIN":
            return Deliverable.objects.all()

        # Client access will be added after assignment ownership validation.
        return Deliverable.objects.none()

    
    def perform_create(self, serializer):
        user = self.request.user

        if user.role != "STUDENT":
            raise PermissionDenied(
                "Only students can create work submissions."
            )

        assignment_id = serializer.validated_data["assignment_id"]
        access_token = self.request.auth

        try:
            assignment = get_assignment(
                assignment_id=assignment_id,
                access_token=access_token,
            )
        except AssignmentNotFoundError:
            from rest_framework.exceptions import NotFound

            raise NotFound("Assignment not found.")
        except AssignmentAuthorizationError:
            raise PermissionDenied(
                "Assignment access was denied."
            )
        except AssignmentServiceUnavailableError:
            raise ServiceUnavailable(
                "Assignment Service is temporarily unavailable."
            )

        assigned_student_id = assignment.get("student_id")

        if str(assigned_student_id) != str(user.user_id):
            raise PermissionDenied(
                "You are not the student assigned to this assignment."
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

        if user.role == "ADMIN":
            return Deliverable.objects.all()

        return Deliverable.objects.none()


class SubmitWorkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, work_id):
        try:
            work = Deliverable.objects.get(id=work_id)
        except Deliverable.DoesNotExist:
            return Response(
                {"error": "Work record not found.", "code": "WORK_NOT_FOUND", "details": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        if (request.user.role != "STUDENT" or str(work.student_id) != str(request.user.user_id)):
            raise PermissionDenied("You cannot submit this work record.")

        if work.status not in [
            Deliverable.Status.DRAFT,
            Deliverable.Status.REVISION_REQUESTED,
        ]:
            return Response(
                {
                    "error": "Only draft work or work requiring revisions can be submitted.",
                    "code": "INVALID_WORK_STATUS",
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

        return Response({
            "data": DeliverableSerializer(work).data,
            "message": "Work submitted successfully.",
        })


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
        from rest_framework.exceptions import NotFound

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
        from rest_framework.exceptions import NotFound

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


class RequestRevisionView(APIView):
    permission_classes = [IsAuthenticated]

    
    def post(self, request, work_id):
        try:
            work = Deliverable.objects.get(id=work_id)
        except Deliverable.DoesNotExist:
            from rest_framework.exceptions import NotFound

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

        return Response({
            "data": DeliverableSerializer(work).data,
            "message": "Revision requested successfully.",
        })




class ApproveWorkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, work_id):
        from decimal import Decimal, InvalidOperation
        from rest_framework.exceptions import NotFound

        try:
            work = Deliverable.objects.get(id=work_id)
        except Deliverable.DoesNotExist:
            raise NotFound("Work record not found.")

        if request.user.role != "CLIENT":
            raise PermissionDenied(
                "Only the project client can approve work."
            )

        assignment, project = verify_client_ownership(work, request)

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
        payment_payload = {
            "assignment_id": assignment_id,
            "payer_id": str(request.user.user_id),
            "payee_id": str(work.student_id),
            "amount": str(amount),
            "idempotency_key": f"work-review-assignment-{assignment_id}",
        }
        access_token = request.auth

        try:
            # A stable key lets a retry reuse the payment request.
            payment_response = post_payment_request(
                "api/payments/",
                payment_payload,
                access_token,
            )
            payment = payment_response["data"]
            payment_id = payment["id"]

            # A previously released payment needs no further processing.
            if payment.get("status") != "RELEASED":
                if payment.get("status") != "SUCCESS":
                    processed_response = process_payment_request(
                        payment_id,
                        access_token,
                    )
                    payment = processed_response["data"]

                if payment.get("status") == "FAILED":
                    raise ValidationError(
                        "Payment processing failed; work has not been approved."
                    )

                if payment.get("status") not in {"SUCCESS", "RELEASED"}:
                    raise ServiceUnavailable(
                        "Payment has not reached a successful state; "
                        "work has not been approved."
                    )

                if payment.get("status") != "RELEASED":
                    released_response = release_payment_request(
                        payment_id,
                        access_token,
                    )
                    payment = released_response["data"]

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

        # Only mark the work approved after release is confirmed.
        with transaction.atomic():
            locked_work = Deliverable.objects.select_for_update().get(
                id=work.id
            )

            # Re-check state after acquiring the lock.
            if locked_work.status == Deliverable.Status.APPROVED:
                return Response({
                    "data": DeliverableSerializer(locked_work).data,
                    "message": "Work has already been approved.",
                })

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
            "data": DeliverableSerializer(locked_work).data,
            "message": "Work approved and payment released successfully.",
        })


class ReviewListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        user = self.request.user

        if user.role == "ADMIN":
            return Review.objects.all()

        return Review.objects.filter(
            models.Q(reviewer_id=user.user_id)
            | models.Q(reviewee_id=user.user_id)
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
