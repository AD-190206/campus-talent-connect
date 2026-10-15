
from rest_framework import serializers
from .models import Payment, Notification


class PaymentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "assignment_id",
            "payer_id",
            "payee_id",
            "amount",
            "idempotency_key",
        ]

        extra_kwargs = {
            "idempotency_key": {
                "required": False,
                "allow_null": True,
                "validators": [],
            },
        }

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Amount must be greater than zero.")
        return value

    def validate(self, attrs):
        if attrs["payer_id"] == attrs["payee_id"]:
            raise serializers.ValidationError(
                "Payer and payee must be different users."
            )
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "assignment_id",
            "payer_id",
            "payee_id",
            "amount",
            "fee",
            "status",
            "transaction_id",
            "idempotency_key",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class NotificationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["user_id", "type", "event", "message"]

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
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
