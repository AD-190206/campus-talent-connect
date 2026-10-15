from rest_framework import serializers

from .models import Deliverable, Review


class DeliverableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deliverable
        fields = [
            "id",
            "assignment_id",
            "student_id",
            "project_id",
            "title",
            "description",
            "submission_url",
            "status",
            "feedback",
            "submitted_at",
            "reviewed_at",
            "payment_requested",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "assignment_id",
            "student_id",
            "project_id",
            "status",
            "feedback",
            "submitted_at",
            "reviewed_at",
            "payment_requested",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        instance = self.instance

        if instance is not None:
            if instance.status not in {
                Deliverable.Status.DRAFT,
                Deliverable.Status.REVISION_REQUESTED,
            }:
                raise serializers.ValidationError(
                    "Work can only be edited while it is a draft "
                    "or requires revisions."
                )

        return attrs


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = [
            "id",
            "assignment_id",
            "reviewer_id",
            "reviewee_id",
            "reviewer_role",
            "rating",
            "comment",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "reviewer_id",
            "reviewer_role",
            "created_at",
        ]

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError(
                "Rating must be between 1 and 5."
            )
        return value


    def validate(self, attrs):
        request = self.context.get("request")
        reviewee_id = attrs.get("reviewee_id")
        assignment_id = attrs.get("assignment_id")

        if request:
            user_id = request.user.user_id

            if reviewee_id and str(reviewee_id) == str(user_id):
                raise serializers.ValidationError({
                    "reviewee_id": "You cannot review yourself."
                })

            if assignment_id and Review.objects.filter(
                assignment_id=assignment_id,
                reviewer_id=user_id,
            ).exists():
                raise serializers.ValidationError({
                    "assignment_id": (
                        "You have already submitted a review "
                        "for this assignment."
                    )
                })

        return attrs
