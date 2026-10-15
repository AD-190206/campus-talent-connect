from rest_framework import serializers
from .models import Application, Assignment, ApplicationStatus, AssignmentStatus


class ApplicationCreateSerializer(serializers.ModelSerializer):
    """Student submits a new application."""

    class Meta:
        model  = Application
        fields = ["id", "student_id", "project_id", "proposal", "resume_url", "status", "created_at"]
        read_only_fields = ["id", "status", "created_at"]


class ApplicationListSerializer(serializers.ModelSerializer):
    """Full application detail — used for listing and retrieving."""

    class Meta:
        model  = Application
        fields = ["id", "student_id", "project_id", "proposal", "resume_url",
                  "status", "created_at", "updated_at"]


class ApplicationUpdateSerializer(serializers.ModelSerializer):
    """Used for PUT — student can update proposal and resume_url only."""

    class Meta:
        model  = Application
        fields = ["proposal", "resume_url"]


class ApplicationStatusUpdateSerializer(serializers.ModelSerializer):
    """Used internally when business shortlists, selects, or rejects."""

    status = serializers.ChoiceField(choices=[
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.SELECTED,
        ApplicationStatus.REJECTED,
    ])

    class Meta:
        model  = Application
        fields = ["status"]

    def validate_status(self, new_status):
        current_status = self.instance.status

        allowed_transitions = {
            ApplicationStatus.SUBMITTED:   [ApplicationStatus.SHORTLISTED, ApplicationStatus.REJECTED],
            ApplicationStatus.SHORTLISTED: [ApplicationStatus.SELECTED,    ApplicationStatus.REJECTED],
        }

        allowed = allowed_transitions.get(current_status, [])

        if new_status not in allowed:
            raise serializers.ValidationError(
                f"Cannot move from '{current_status}' to '{new_status}'. "
                f"Allowed: {[s for s in allowed]}"
            )

        return new_status


class ApplicationWithdrawSerializer(serializers.ModelSerializer):
    """Student withdraws their own application."""

    class Meta:
        model  = Application
        fields = ["status"]

    def validate(self, attrs):
        current_status = self.instance.status
        terminal = [ApplicationStatus.SELECTED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]

        if current_status in terminal:
            raise serializers.ValidationError(
                f"Cannot withdraw an application with status '{current_status}'."
            )
        return attrs


class AssignmentSerializer(serializers.ModelSerializer):
    """Full assignment detail — used by Person 4 (Work & Review) and Person 5 (Payment)."""

    class Meta:
        model  = Assignment
        fields = ["id", "application_id", "student_id", "project_id",
                  "status", "assigned_date", "completion_date"]