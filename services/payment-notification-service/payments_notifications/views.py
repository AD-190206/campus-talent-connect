import logging
from uuid import UUID
from decimal import Decimal
from django.core.paginator import EmptyPage, Paginator
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
    PaymentServiceError,
    create_payment,
    process_payment,
    release_payment,
)
from .integrations import (
    UpstreamServiceError,
    get_assignment,
    get_project,
)

logger = logging.getLogger(__name__)


def error_response(message, code, http_status, details=None):
    return Response(
        {
            "error": message,
            "code": code,
            "details": details if details is not None else {},
        },
        status=http_status,
    )


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "service": "payment-notification-service",
            "status": "running",
        })


class PaymentListCreateView(APIView):

    def get(self, request):
        user_id = getattr(request.user, "id", None)

        if not user_id:
            return error_response(
                "Authenticated user could not be identified.",
                "AUTHENTICATED_USER_NOT_FOUND",
                status.HTTP_401_UNAUTHORIZED,
            )

        queryset = (
            Payment.objects.filter(payer_id=user_id)
            | Payment.objects.filter(payee_id=user_id)
        )
        queryset = queryset.distinct().order_by("-created_at", "-id")

        try:
            page = int(request.query_params.get("page", "1"))
            page_size = int(request.query_params.get("page_size", "20"))
        except (TypeError, ValueError):
            return error_response(
                "page and page_size must be integers.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        if page < 1 or page_size < 1 or page_size > 100:
            return error_response(
                "page must be at least 1 and page_size must be between 1 and 100.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        paginator = Paginator(queryset, page_size)

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            return error_response(
                "Requested page does not exist.",
                "PAGE_NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "data": PaymentSerializer(page_obj.object_list, many=True).data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
            "message": "Payment history retrieved successfully",
        })

    def post(self, request):
        user_id = getattr(request.user, "id", None)

        if not user_id:
            return error_response(
                "Authenticated user could not be identified.",
                "AUTHENTICATED_USER_NOT_FOUND",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = PaymentCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Request validation failed.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
                details=serializer.errors,
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
                    "payee_id": [
                        "Payer and payee must be different users."
                    ]
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
                "AUTHENTICATED_USER_NOT_FOUND",
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
                "AUTHENTICATION_REQUIRED",
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
                "INVALID_SIMULATION_OPTION",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = process_payment(
                payment,
                simulate_failure=simulate_failure,
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
                "AUTHENTICATION_REQUIRED",
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
                "AUTHENTICATED_USER_NOT_FOUND",
                status.HTTP_401_UNAUTHORIZED,
            )

        queryset = Notification.objects.filter(user_id=user_id)

        unread = request.query_params.get("unread")
        if unread == "true":
            queryset = queryset.filter(is_read=False)
        elif unread == "false":
            queryset = queryset.filter(is_read=True)

        try:
            page = int(request.query_params.get("page", "1"))
            page_size = int(request.query_params.get("page_size", "20"))
        except (TypeError, ValueError):
            return error_response(
                "page and page_size must be integers.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        if page < 1 or page_size < 1 or page_size > 100:
            return error_response(
                "page must be at least 1 and page_size must be between 1 and 100.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        paginator = Paginator(queryset, page_size)

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            return error_response(
                "Requested page does not exist.",
                "PAGE_NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "data": NotificationSerializer(
                page_obj.object_list,
                many=True,
            ).data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": paginator.count,
                "total_pages": paginator.num_pages,
            },
            "message": "Notifications retrieved successfully",
        })

    def post(self, request):
        authenticated_user_id = getattr(request.user, "id", None)

        if not authenticated_user_id:
            return error_response(
                "Authenticated user could not be identified.",
                "AUTHENTICATED_USER_NOT_FOUND",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = NotificationCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                "Request validation failed.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
                details=serializer.errors,
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
