from .services import PaymentServiceError, create_payment, process_payment, release_payment
from uuid import UUID
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from rest_framework import status
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


def error_response(message, code, http_status):
    return Response(
        {"error": message, "code": code},
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
        queryset = Payment.objects.all()

        user_id = request.query_params.get("user_id")
        if user_id:
            try:
                UUID(user_id)
            except ValueError:
                return error_response(
                    "user_id must be a valid UUID",
                    "INVALID_USER_ID",
                    status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(
                payer_id=user_id
            ) | queryset.filter(payee_id=user_id)

        return Response({
            "data": PaymentSerializer(queryset.distinct(), many=True).data,
            "message": "Payment history retrieved successfully",
        })

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                serializer.errors,
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment, created = create_payment(serializer.validated_data)

        except PaymentServiceError as exc:
            return error_response(
                str(exc),
                "IDEMPOTENCY_KEY_CONFLICT",
                status.HTTP_409_CONFLICT,
            )

        except Exception:
            return error_response(
                "Could not create payment. Check the request and try again.",
                "PAYMENT_CREATION_FAILED",
                status.HTTP_400_BAD_REQUEST,
            )

        response_status = (
            status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
        return Response({
            "data": PaymentSerializer(payment).data,
            "message": (
                "Payment created successfully"
                if created
                else "Existing payment returned for this idempotency key"
            ),
        }, status=response_status)


class PaymentDetailView(APIView):
    def get(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id)
        return Response({
            "data": PaymentSerializer(payment).data,
            "message": "Payment retrieved successfully",
        })


class ProcessPaymentView(APIView):
    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id)

        simulate_failure = request.data.get("simulate_failure", False)
        if not isinstance(simulate_failure, bool):
            return error_response(
                "simulate_failure must be true or false",
                "INVALID_SIMULATION_OPTION",
                status.HTTP_400_BAD_REQUEST,
            )

        payment = process_payment(
            payment,
            simulate_failure=simulate_failure,
        )
        return Response({
            "data": PaymentSerializer(payment).data,
            "message": "Mock payment processing completed",
        })


class ReleasePaymentView(APIView):
    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id)

        try:
            payment = release_payment(payment)
        except PaymentServiceError as exc:
            return error_response(
                str(exc),
                "PAYMENT_RELEASE_NOT_ALLOWED",
                status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "data": PaymentSerializer(payment).data,
            "message": "Payment marked as released",
        })


class NotificationListCreateView(APIView):
    def get(self, request):
        queryset = Notification.objects.all()

        user_id = request.query_params.get("user_id")
        if user_id:
            try:
                UUID(user_id)
            except ValueError:
                return error_response(
                    "user_id must be a valid UUID",
                    "INVALID_USER_ID",
                    status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(user_id=user_id)

        unread = request.query_params.get("unread")
        if unread == "true":
            queryset = queryset.filter(is_read=False)
        elif unread == "false":
            queryset = queryset.filter(is_read=True)

        return Response({
            "data": NotificationSerializer(queryset, many=True).data,
            "message": "Notifications retrieved successfully",
        })

    def post(self, request):
        serializer = NotificationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                serializer.errors,
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        notification = serializer.save()
        return Response({
            "data": NotificationSerializer(notification).data,
            "message": "Notification created successfully",
        }, status=status.HTTP_201_CREATED)
