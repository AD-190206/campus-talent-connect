import uuid
from django.db import models


class ApplicationStatus(models.TextChoices):
    SUBMITTED   = "submitted",   "Submitted"
    SHORTLISTED = "shortlisted", "Shortlisted"
    SELECTED    = "selected",    "Selected"
    REJECTED    = "rejected",    "Rejected"
    WITHDRAWN   = "withdrawn",   "Withdrawn"


class AssignmentStatus(models.TextChoices):
    ACTIVE    = "active",    "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class Application(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_id = models.UUIDField()
    project_id = models.UUIDField()
    proposal   = models.TextField()
    resume_url = models.URLField(blank=True, default="")
    status     = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.SUBMITTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student_id", "project_id")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Application {self.id} | student={self.student_id} project={self.project_id} [{self.status}]"


class Assignment(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application_id = models.UUIDField(unique=True)
    student_id     = models.UUIDField()
    client_id      = models.UUIDField(default=uuid.UUID("00000000-0000-0000-0000-000000000000"))
    project_id     = models.UUIDField()
    status         = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE,
    )
    assigned_date   = models.DateTimeField(auto_now_add=True)
    completion_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_date"]

    def __str__(self):
        return f"Assignment {self.id} | student={self.student_id} project={self.project_id} [{self.status}]"
