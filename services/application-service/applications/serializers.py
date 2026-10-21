from rest_framework import serializers

from .models import Application, Assignment


class StrictFieldsMixin:
    """Reject unknown and read-only fields instead of silently ignoring them.

    Identity (`student_id`) and `status` must never come from the body.
    """

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            writable = {
                name for name, field in self.fields.items() if not field.read_only
            }
            unknown = sorted(k for k in data.keys() if k not in writable)
            if unknown:
                raise serializers.ValidationError(
                    {name: ["Unknown or read-only field."] for name in unknown}
                )
        return super().to_internal_value(data)


class ApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = [
            "id",
            "student_id",
            "project_id",
            "proposal",
            "resume_url",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ApplicationCreateSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = ["project_id", "proposal", "resume_url"]

    def validate_proposal(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Proposal cannot be empty.")
        return value


class ApplicationUpdateSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Application
        fields = ["proposal", "resume_url"]

    def validate_proposal(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Proposal cannot be empty.")
        return value


class AssignmentSerializer(serializers.ModelSerializer):
    """Shared shape consumed by Work & Review and Payment."""

    class Meta:
        model = Assignment
        fields = [
            "id",
            "application_id",
            "student_id",
            "client_id",
            "project_id",
            "status",
            "assigned_date",
            "completion_date",
        ]
        read_only_fields = fields
