import uuid
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction

from .models import Payment, Notification


# Only a mock provider exists in this iteration (contract decision 9). Every
# payment response reports this so it is never mistaken for a live gateway.
PAYMENT_PROVIDER = "MOCK"

# Payments in these statuses no longer block a new payment for the assignment.
INACTIVE_STATUSES = (Payment.Status.FAILED, Payment.Status.REFUNDED)


class PaymentServiceError(Exception):
    pass


class DuplicateAssignmentPayment(PaymentServiceError):
    """An active payment already exists for the assignment."""

    def __init__(self, payment):
        super().__init__("An active payment already exists for this assignment.")
        self.payment = payment


class MockPaymentsDisabled(PaymentServiceError):
    """Processing was requested while the mock provider is switched off."""


def create_payment(validated_data):
    """
    Create a pending payment.
    Reuse a payment only when the same idempotency key has matching details.
    """
    key = validated_data.get("idempotency_key")

    if not isinstance(key, str) or not key.strip():
        raise PaymentServiceError(
            "A non-empty idempotency key is required."
        )

    key = key.strip()

    def find_existing():
        return Payment.objects.filter(idempotency_key=key).first()

    def matches(existing):
        fields_to_compare = (
            "assignment_id",
            "payer_id",
            "payee_id",
            "amount",
        )
        return all(
            getattr(existing, field) == validated_data[field]
            for field in fields_to_compare
        )

    existing = find_existing()
    if existing:
        if matches(existing):
            return existing, False
        raise PaymentServiceError(
            "This idempotency key was already used with different payment details."
        )

    active = (
        Payment.objects.filter(assignment_id=validated_data["assignment_id"])
        .exclude(status__in=INACTIVE_STATUSES)
        .first()
    )
    if active:
        raise DuplicateAssignmentPayment(active)

    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                **validated_data,
                fee=Decimal("0.00"),
            )
        return payment, True
    except IntegrityError:
        # A concurrent request may have created the same key.
        existing = find_existing()
        if existing:
            if matches(existing):
                return existing, False
            raise PaymentServiceError(
                "This idempotency key was already used with different payment details."
            )
        raise


def process_payment(payment, simulate_failure=False):
    """
    Process a payment using a mock gateway.
    Update payment status and create notifications atomically.
    """
    if not settings.MOCK_PAYMENT_ENABLED:
        raise MockPaymentsDisabled(
            "Mock payment processing is disabled. "
            "Configure a real payment gateway or explicitly enable "
            "mock payments for development."
        )
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)

        terminal_statuses = (
            Payment.Status.SUCCESS,
            Payment.Status.FAILED,
            Payment.Status.RELEASED,
            Payment.Status.REFUNDED,
        )

        if payment.status in terminal_statuses:
            return payment

        payment.status = Payment.Status.PROCESSING
        payment.save(update_fields=["status", "updated_at"])

        if simulate_failure:
            payment.status = Payment.Status.FAILED
        else:
            payment.status = Payment.Status.SUCCESS
            if not payment.transaction_id:
                payment.transaction_id = (
                    f"MOCK-{uuid.uuid4().hex[:16].upper()}"
                )

        payment.save(
            update_fields=["status", "transaction_id", "updated_at"]
        )

        outcome = (
            "succeeded"
            if payment.status == Payment.Status.SUCCESS
            else "failed"
        )

        for user_id in {payment.payer_id, payment.payee_id}:
            Notification.objects.create(
                user_id=user_id,
                type=Notification.NotificationType.IN_APP,
                event=f"PAYMENT_{payment.status}",
                message=f"Payment {payment.id} has {outcome}.",
            )

        return payment


def release_payment(payment):
    """Release a successful payment to the payee exactly once."""
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)

        if payment.status == Payment.Status.RELEASED:
            return payment

        if payment.status != Payment.Status.SUCCESS:
            raise PaymentServiceError(
                "Only successful payments can be released."
            )

        payment.status = Payment.Status.RELEASED
        payment.save(update_fields=["status", "updated_at"])

        Notification.objects.create(
            user_id=payment.payee_id,
            type=Notification.NotificationType.IN_APP,
            event="PAYMENT_RELEASED",
            message=(
                f"Payment {payment.id} of {payment.amount - payment.fee} "
                f"has been released to you."
            ),
        )
        Notification.objects.create(
            user_id=payment.payer_id,
            type=Notification.NotificationType.IN_APP,
            event="PAYMENT_RELEASED",
            message=f"Payment {payment.id} has been released to the student.",
        )

        return payment
