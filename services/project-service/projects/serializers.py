from rest_framework import serializers

from .models import Project


class StrictFieldsMixin:
    """Reject unknown and read-only fields instead of silently ignoring them.

    The contract says identity and status must never come from the request
    body, so a body containing `client_id` or `status` is an error.
    """

    def to_internal_value(self, data):
        if hasattr(data, "keys"):
            writable = {
                name
                for name, field in self.fields.items()
                if not field.read_only
            }
            unknown = sorted(k for k in data.keys() if k not in writable)
            if unknown:
                raise serializers.ValidationError(
                    {
                        name: ["Unknown or read-only field."]
                        for name in unknown
                    }
                )
        return super().to_internal_value(data)


class ProjectSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id",
            "client_id",
            "title",
            "description",
            "skills",
            "category",
            "budget",
            "deadline",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "client_id",
            "status",
            "created_at",
            "updated_at",
        ]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "Project title cannot be empty."
            )
        return value

    def validate_description(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "Project description cannot be empty."
            )
        return value

    def validate_budget(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Budget must be greater than zero."
            )
        return value

    def validate_skills(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Skills must be a list.")

        if not all(
            isinstance(skill, str) and skill.strip() for skill in value
        ):
            raise serializers.ValidationError(
                "Each skill must be a non-empty string."
            )

        return [skill.strip() for skill in value]

    def validate_category(self, value):
        return value.strip()