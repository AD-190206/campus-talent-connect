
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction

from .models import Payment, Notification


class PaymentServiceError(Exception):
    pass


def create_payment(validated_data):
    """
    Create a pending payment.
    Reuse a payment only when the same idempotency key has matching details.
    """
    key = validated_data.get("idempotency_key")

    def find_existing():
        if not key:
            return None
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
    """Represent release of a successful payment to the payee."""
    if payment.status != Payment.Status.SUCCESS:
        raise PaymentServiceError(
            "Only successful payments can be released."
        )

    payment.status = Payment.Status.RELEASED
    payment.save(update_fields=["status", "updated_at"])
    return payment
