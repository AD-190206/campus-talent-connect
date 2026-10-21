import logging
import math
from uuid import UUID
from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Payment, Notification
from .serializers import (
    PaymentCreateSerializer,
    PaymentSerializer,
    NotificationCreateSerializer,
    NotificationSerializer,
)
from .services import (
    PAYMENT_PROVIDER,
    DuplicateAssignmentPayment,
    MockPaymentsDisabled,
    PaymentServiceError,
    create_payment,
    process_payment,
    release_payment,
)
from .integrations import (
    UpstreamServiceError,
    get_assignment,
    get_project,
    get_work_for_assignment,
)

logger = logging.getLogger(__name__)

# Work statuses that make a payment eligible for release.
RELEASABLE_WORK_STATUSES = {"SUBMITTED", "APPROVED"}


def error_response(message, code, http_status, details=None):
    return Response(
        {
            "error": message,
            "code": code,
            "details": details if details is not None else {},
        },
        status=http_status,
    )


def paginated_response(request, queryset, serializer_class, message):
    """Collection envelope with contract pagination, or a 400 error."""
    try:
        page = int(request.query_params.get("page", "1"))
        page_size = int(request.query_params.get("page_size", "20"))
    except (TypeError, ValueError):
        page = page_size = 0

    if page < 1 or page_size < 1 or page_size > 100:
        return error_response(
            "page must be at least 1 and page_size must be between 1 and 100.",
            "VALIDATION_ERROR",
            status.HTTP_400_BAD_REQUEST,
            details={
                "fields": {
                    "page": ["Must be an integer of at least 1."],
                    "page_size": ["Must be an integer between 1 and 100."],
                }
            },
        )

    total = queryset.count()
    offset = (page - 1) * page_size

    return Response({
        "data": serializer_class(
            queryset[offset:offset + page_size], many=True
        ).data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if total else 0,
        },
        "message": message,
    })


def uuid_query_param(request, name):
    """Return (uuid_or_None, error_response_or_None)."""
    raw = request.query_params.get(name)
    if not raw:
        return None, None
    try:
        return UUID(raw), None
    except ValueError:
        return None, error_response(
            "Invalid query parameter.",
            "VALIDATION_ERROR",
            status.HTTP_400_BAD_REQUEST,
            details={"fields": {name: ["Must be a valid UUID."]}},
        )


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "data": {
                "service": "payment-notification-service",
                "status": "healthy",
                "payment_mode": PAYMENT_PROVIDER,
            },
            "message": "Health check successful",
        })


class PaymentListCreateView(APIView):

    def get(self, request):
        user_id = getattr(request.user, "id", None)

        if not user_id:
            return error_response(
                "Authenticated user could not be identified.",
                "UNAUTHORIZED",
                status.HTTP_401_UNAUTHORIZED,
            )

        queryset = (
            Payment.objects.filter(payer_id=user_id)
            | Payment.objects.filter(payee_id=user_id)
        )

        assignment_id, err = uuid_query_param(request, "assignment_id")
        if err:
            return err
        if assignment_id:
            queryset = queryset.filter(assignment_id=assignment_id)

        payment_status = request.query_params.get("status")
        if payment_status:
            queryset = queryset.filter(status=payment_status)

        return paginated_response(
            request,
            queryset.distinct().order_by("-created_at", "-id"),
            PaymentSerializer,
            "Payment history retrieved successfully",
        )

    def post(self, request):
        user_id = getattr(request.user, "id", None)

        if not user_id:
            return error_response(
                "Authenticated user could not be identified.",
                "UNAUTHORIZED",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = PaymentCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Request validation failed.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
                details={"fields": serializer.errors},
            )
        supplied_payer_id = request.data.get("payer_id")

        if supplied_payer_id is not None and str(supplied_payer_id) != str(user_id):
            return error_response(
                "Payer ID must match the authenticated user.",
                "PAYER_ID_MISMATCH",
                status.HTTP_403_FORBIDDEN,
            )

        payment_data = dict(serializer.validated_data)
        payment_data["payer_id"] = UUID(str(user_id))

        if str(payment_data["payer_id"]) == str(payment_data["payee_id"]):
            return error_response(
                "Payer and payee must be different users.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
                details={
                    "fields": {
                        "payee_id": ["Payer and payee must be different users."]
                    }
                },
            )

        authorization = request.headers.get("Authorization")

        try:
            assignment = get_assignment(
                payment_data["assignment_id"],
                authorization,
            )

            if not isinstance(assignment, dict):
                return error_response(
                    "Assignment service returned invalid data.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            project_id = assignment.get("project_id")
            student_id = assignment.get("student_id")

            if not project_id or not student_id:
                return error_response(
                    "Assignment response is missing required fields.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            if str(student_id) != str(payment_data["payee_id"]):
                return error_response(
                    "Payee must be the student assigned to this assignment.",
                    "PAYEE_ASSIGNMENT_MISMATCH",
                    status.HTTP_400_BAD_REQUEST,
                )

            project = get_project(project_id, authorization)

            if not isinstance(project, dict):
                return error_response(
                    "Project service returned invalid data.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            client_id = project.get("client_id")
            budget = project.get("budget")

            if not client_id or budget is None:
                return error_response(
                    "Project response is missing required fields.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            if str(client_id) != str(payment_data["payer_id"]):
                return error_response(
                    "Only the project's client can initiate this payment.",
                    "PAYER_PROJECT_MISMATCH",
                    status.HTTP_403_FORBIDDEN,
                )

            try:
                project_budget = Decimal(str(budget))
            except Exception:
                return error_response(
                    "Project service returned an invalid budget.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            if not project_budget.is_finite() or project_budget <= 0:
                return error_response(
                    "Project service returned an invalid budget.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            payment_data["amount"] = project_budget.quantize(Decimal("0.01"))

        except UpstreamServiceError as exc:
            return error_response(
                str(exc),
                exc.code,
                exc.http_status,
            )
        try:
            payment, created = create_payment(payment_data)
        except DuplicateAssignmentPayment as exc:
            return error_response(
                str(exc),
                "CONFLICT",
                status.HTTP_409_CONFLICT,
                details={"payment_id": str(exc.payment.id)},
            )
        except PaymentServiceError as exc:
            return error_response(
                str(exc),
                "IDEMPOTENCY_KEY_CONFLICT",
                status.HTTP_409_CONFLICT,
            )

        response_status = (
            status.HTTP_201_CREATED
            if created
            else status.HTTP_200_OK
        )

        return Response(
            {
                "data": PaymentSerializer(payment).data,
                "message": (
                    "Payment created successfully"
                    if created
                    else "Existing payment returned successfully"
                ),
            },
            status=response_status,
        )

class PaymentDetailView(APIView):
    def get(self, request, payment_id):
        user_id = getattr(request.user, "id", None)
        role = getattr(request.user, "role", None)

        if not user_id:
            return error_response(
                "Authenticated user could not be identified.",
                "UNAUTHORIZED",
                status.HTTP_401_UNAUTHORIZED,
            )

        if role == "ADMIN":
            payment = get_object_or_404(
                Payment,
                id=payment_id,
            )
        else:
            payment = get_object_or_404(
                Payment.objects.filter(
                    payer_id=user_id
                ) | Payment.objects.filter(
                    payee_id=user_id
                ),
                id=payment_id,
            )

        return Response({
            "data": PaymentSerializer(payment).data,
            "message": "Payment retrieved successfully",
        })



class ProcessPaymentView(APIView):
    def post(self, request, payment_id):
        user_id = getattr(request.user, "id", None)

        if not user_id:
            return error_response(
                "Authentication is required.",
                "UNAUTHORIZED",
                status.HTTP_401_UNAUTHORIZED,
            )

        # Only the payment's payer can process it.
        payment = get_object_or_404(
            Payment.objects.filter(payer_id=user_id),
            id=payment_id,
        )

        simulate_failure = request.data.get("simulate_failure", False)

        if not isinstance(simulate_failure, bool):
            return error_response(
                "simulate_failure must be a boolean.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
                details={"fields": {"simulate_failure": ["Must be a boolean."]}},
            )

        try:
            payment = process_payment(
                payment,
                simulate_failure=simulate_failure,
            )
        except MockPaymentsDisabled:
            return error_response(
                "No payment provider is configured. Set "
                "MOCK_PAYMENT_ENABLED=1 to use the development mock provider.",
                "PAYMENT_PROVIDER_UNAVAILABLE",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except PaymentServiceError:
            return error_response(
                "Payment processing failed.",
                "PAYMENT_PROCESSING_FAILED",
                status.HTTP_409_CONFLICT,
            )

        return Response({
            "data": PaymentSerializer(payment).data,
            "message": "Mock payment processing completed",
        })


class ReleasePaymentView(APIView):
    def post(self, request, payment_id):
        user_id = getattr(request.user, "id", None)

        if not user_id:
            return error_response(
                "Authentication is required.",
                "UNAUTHORIZED",
                status.HTTP_401_UNAUTHORIZED,
            )

        payment = get_object_or_404(
            Payment.objects.filter(payer_id=user_id),
            id=payment_id,
        )

        authorization = request.headers.get("Authorization")

        try:
            assignment = get_assignment(
                payment.assignment_id,
                authorization,
            )

            if not isinstance(assignment, dict):
                return error_response(
                    "Assignment service returned invalid data.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            project_id = assignment.get("project_id")
            student_id = assignment.get("student_id")

            if not project_id or not student_id:
                return error_response(
                    "Assignment service response is incomplete.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            if str(student_id) != str(payment.payee_id):
                return error_response(
                    "Payment payee does not match the assignment student.",
                    "PAYEE_ASSIGNMENT_MISMATCH",
                    status.HTTP_409_CONFLICT,
                )

            project = get_project(project_id, authorization)

            if not isinstance(project, dict):
                return error_response(
                    "Project service returned invalid data.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            client_id = project.get("client_id")

            if not client_id:
                return error_response(
                    "Project service response is incomplete.",
                    "UPSTREAM_INVALID_RESPONSE",
                    status.HTTP_502_BAD_GATEWAY,
                )

            if str(client_id) != str(payment.payer_id):
                return error_response(
                    "Payment payer does not own the project.",
                    "PAYER_PROJECT_MISMATCH",
                    status.HTTP_403_FORBIDDEN,
                )

            # Release eligibility: the student must have submitted work for
            # this assignment. Work & Review calls release while approving.
            if payment.status != Payment.Status.RELEASED:
                work_items = get_work_for_assignment(
                    payment.assignment_id,
                    authorization,
                )

                if not isinstance(work_items, list):
                    return error_response(
                        "Work & Review service returned invalid data.",
                        "UPSTREAM_INVALID_RESPONSE",
                        status.HTTP_502_BAD_GATEWAY,
                    )

                if not any(
                    isinstance(item, dict)
                    and item.get("status") in RELEASABLE_WORK_STATUSES
                    for item in work_items
                ):
                    return error_response(
                        "Payment cannot be released before work is "
                        "submitted for this assignment.",
                        "PAYMENT_RELEASE_NOT_ALLOWED",
                        status.HTTP_409_CONFLICT,
                    )

            payment = release_payment(payment)

        except UpstreamServiceError as exc:
            return error_response(
                str(exc),
                exc.code,
                exc.http_status,
            )
        except PaymentServiceError:
            return error_response(
                "Payment release is not allowed.",
                "PAYMENT_RELEASE_NOT_ALLOWED",
                status.HTTP_409_CONFLICT,
            )

        return Response({
            "data": PaymentSerializer(payment).data,
            "message": "Payment marked as released",
        })

class NotificationListCreateView(APIView):

    def get(self, request):
        user_id = getattr(request.user, "id", None)

        if not user_id:
            return error_response(
                "Authenticated user could not be identified.",
                "UNAUTHORIZED",
                status.HTTP_401_UNAUTHORIZED,
            )

        queryset = Notification.objects.filter(user_id=user_id)

        unread = request.query_params.get("unread")
        if unread == "true":
            queryset = queryset.filter(is_read=False)
        elif unread == "false":
            queryset = queryset.filter(is_read=True)

        return paginated_response(
            request,
            queryset.order_by("-created_at", "-id"),
            NotificationSerializer,
            "Notifications retrieved successfully",
        )

    def post(self, request):
        authenticated_user_id = getattr(request.user, "id", None)

        if not authenticated_user_id:
            return error_response(
                "Authenticated user could not be identified.",
                "UNAUTHORIZED",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = NotificationCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Request validation failed.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
                details={"fields": serializer.errors},
            )

        target_user_id = serializer.validated_data["user_id"]

        if str(target_user_id) != str(authenticated_user_id):
            return error_response(
                "You can only create notifications for your own account.",
                "NOTIFICATION_USER_MISMATCH",
                status.HTTP_403_FORBIDDEN,
            )

        notification = serializer.save()

        return Response({
            "data": NotificationSerializer(notification).data,
            "message": "Notification created successfully",
        }, status=status.HTTP_201_CREATED)
