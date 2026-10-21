from rest_framework import serializers
from .models import Payment, Notification


class PaymentCreateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Payment
        fields = [
            "assignment_id",
            "payee_id",
            "idempotency_key",
        ]

        extra_kwargs = {
            "idempotency_key": {
                "required": True,
                "allow_null": False,
                "allow_blank": False,
                "validators": [],
            },
        }



class PaymentSerializer(serializers.ModelSerializer):
    # Fee is explicit: the platform currently charges no fee, so the payee
    # receives the full project budget (net_amount = amount - fee).
    net_amount = serializers.SerializerMethodField()
    payment_mode = serializers.SerializerMethodField()

    def get_net_amount(self, payment):
        return str(payment.amount - payment.fee)

    def get_payment_mode(self, payment):
        from .services import PAYMENT_PROVIDER

        return PAYMENT_PROVIDER

    class Meta:
        model = Payment
        fields = [
            "id",
            "assignment_id",
            "payer_id",
            "payee_id",
            "amount",
            "fee",
            "net_amount",
            "payment_mode",
            "status",
            "transaction_id",
            "idempotency_key",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class NotificationCreateSerializer(serializers.ModelSerializer):
    message = serializers.CharField(
        required=True,
        allow_null=False,
        allow_blank=False,
        trim_whitespace=True,
    )

    class Meta:
        model = Notification
        fields = ["user_id", "type", "event", "message"]

    def validate_message(self, value):
        if not value:
            raise serializers.ValidationError(
                "Message cannot be empty."
            )
        return value


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "user_id",
            "type",
            "event",
            "message",
            "is_read",
            "created_at",
        ]
        read_only_fields = ["id", "is_read", "created_at"]
