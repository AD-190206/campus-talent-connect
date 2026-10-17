from django.utils import timezone
from django.db import IntegrityError, models, transaction
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Deliverable, Review
from .serializers import DeliverableSerializer, ReviewSerializer


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
        if self.request.user.role != "STUDENT":
            raise PermissionDenied("Only students can create work submissions.")

        serializer.save(student_id=self.request.user.user_id)


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
                {"error": "Work record not found.", "code": "WORK_NOT_FOUND"},
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
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not work.submission_url:
            return Response(
                {
                    "error": "Provide a submission URL before submitting work.",
                    "code": "SUBMISSION_URL_REQUIRED",
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


class RequestRevisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, work_id):
        from django.utils import timezone
        from rest_framework.exceptions import PermissionDenied
        from rest_framework import status
        from rest_framework.response import Response

        try:
            work = Deliverable.objects.get(id=work_id)
        except Deliverable.DoesNotExist:
            return Response(
                {
                    "error": "Work record not found.",
                    "code": "WORK_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Do not allow students to request revisions on their own work.
        if request.user.role != "CLIENT":
            raise PermissionDenied(
                "Only the project client can request revisions."
            )

        # The client must be verified against the assignment/project owner.
        # That integration is not implemented yet, so fail closed.
        return Response(
            {
                "error": "Client ownership verification is not yet configured.",
                "code": "OWNERSHIP_VERIFICATION_UNAVAILABLE",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class ApproveWorkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, work_id):
        from rest_framework import status
        from rest_framework.exceptions import PermissionDenied
        from rest_framework.response import Response

        try:
            work = Deliverable.objects.get(id=work_id)
        except Deliverable.DoesNotExist:
            return Response(
                {
                    "error": "Work record not found.",
                    "code": "WORK_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.role != "CLIENT":
            raise PermissionDenied(
                "Only the project client can approve work."
            )

        return Response(
            {
                "error": "Client ownership verification is not yet configured.",
                "code": "OWNERSHIP_VERIFICATION_UNAVAILABLE",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

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
