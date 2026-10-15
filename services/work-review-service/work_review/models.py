
import uuid

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Deliverable(models.Model):
    """Work submitted by a student for an assigned project."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        REVISION_REQUESTED = "REVISION_REQUESTED", "Revision Requested"
        APPROVED = "APPROVED", "Approved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # These IDs belong to other services; they are not foreign keys.
    assignment_id = models.UUIDField(db_index=True)
    student_id = models.UUIDField(db_index=True)
    project_id = models.UUIDField(db_index=True)

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    submission_url = models.URLField(max_length=1000, blank=True)

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )

    feedback = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Prevents duplicate payment requests when approval is retried.
    payment_requested = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["assignment_id", "status"]),
            models.Index(fields=["student_id", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"


class Review(models.Model):
    """A student's or client's rating after an assignment is completed."""

    class ReviewerRole(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        CLIENT = "CLIENT", "Client"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    assignment_id = models.UUIDField(db_index=True)
    reviewer_id = models.UUIDField(db_index=True)
    reviewee_id = models.UUIDField(db_index=True)

    reviewer_role = models.CharField(
        max_length=10,
        choices=ReviewerRole.choices,
    )

    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment_id", "reviewer_id"],
                name="unique_review_per_assignment_reviewer",
            )
        ]

    def __str__(self):
        return f"{self.rating}/5 for assignment {self.assignment_id}"
