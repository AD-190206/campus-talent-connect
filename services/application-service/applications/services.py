"""Application and assignment business rules.

The service layer is the only place that changes statuses; every transition
is checked against the tables below and persisted under a row lock.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from .api import ApiError
from .models import Application, ApplicationStatus, Assignment, AssignmentStatus

ALLOWED_TRANSITIONS = {
    ApplicationStatus.SUBMITTED: {
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SHORTLISTED: {
        ApplicationStatus.SELECTED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    },
    ApplicationStatus.SELECTED: set(),
    ApplicationStatus.REJECTED: set(),
    ApplicationStatus.WITHDRAWN: set(),
}

# Statuses in which the applicant may still edit the proposal.
EDITABLE_STATUSES = {ApplicationStatus.SUBMITTED}


def _transition(application, target):
    if target not in ALLOWED_TRANSITIONS[application.status]:
        raise ApiError(
            f"Cannot move application from '{application.status}' to '{target}'.",
            "INVALID_STATE_TRANSITION",
        )
    application.status = target
    application.save(update_fields=["status", "updated_at"])
    return application


def _locked(application_id):
    return Application.objects.select_for_update().get(id=application_id)


def create_application(*, student_id, project_id, proposal, resume_url=""):
    try:
        with transaction.atomic():
            return Application.objects.create(
                student_id=student_id,
                project_id=project_id,
                proposal=proposal,
                resume_url=resume_url,
            )
    except IntegrityError:
        raise ApiError(
            "You have already applied to this project.",
            "DUPLICATE_APPLICATION",
            409,
        )


def update_application(application, **fields):
    with transaction.atomic():
        application = _locked(application.id)
        if application.status not in EDITABLE_STATUSES:
            raise ApiError(
                "Only submitted applications can be edited.",
                "INVALID_STATE_TRANSITION",
            )
        for name, value in fields.items():
            setattr(application, name, value)
        application.save()
        return application


def shortlist_application(application):
    with transaction.atomic():
        return _transition(_locked(application.id), ApplicationStatus.SHORTLISTED)


def reject_application(application):
    with transaction.atomic():
        return _transition(_locked(application.id), ApplicationStatus.REJECTED)


def withdraw_application(application):
    with transaction.atomic():
        return _transition(_locked(application.id), ApplicationStatus.WITHDRAWN)


def select_application(application, *, client_id, on_assigned=None):
    """Select an applicant and create the assignment in one transaction.

    `on_assigned` runs inside the transaction after the assignment row is
    written (used to move the project to IN_PROGRESS); if it raises, the
    selection and assignment are rolled back.

    Other open applications for the same project are rejected, because a
    project has exactly one assigned student.
    """
    with transaction.atomic():
        application = _locked(application.id)

        if Assignment.objects.filter(project_id=application.project_id).exists():
            raise ApiError(
                "This project already has an assigned student.",
                "CONFLICT",
                409,
            )

        _transition(application, ApplicationStatus.SELECTED)

        assignment = Assignment.objects.create(
            application_id=application.id,
            student_id=application.student_id,
            client_id=client_id,
            project_id=application.project_id,
            status=AssignmentStatus.ACTIVE,
        )

        Application.objects.filter(
            project_id=application.project_id,
            status__in=[ApplicationStatus.SUBMITTED, ApplicationStatus.SHORTLISTED],
        ).exclude(id=application.id).update(
            status=ApplicationStatus.REJECTED, updated_at=timezone.now()
        )

        if on_assigned is not None:
            on_assigned(assignment)

    return application, assignment


def complete_assignment(assignment):
    """Mark an assignment completed. Repeating the call is a no-op."""
    with transaction.atomic():
        assignment = Assignment.objects.select_for_update().get(id=assignment.id)

        if assignment.status == AssignmentStatus.COMPLETED:
            return assignment

        if assignment.status != AssignmentStatus.ACTIVE:
            raise ApiError(
                "Only active assignments can be completed.",
                "INVALID_STATE_TRANSITION",
            )

        assignment.status = AssignmentStatus.COMPLETED
        assignment.completion_date = timezone.now()
        assignment.save(update_fields=["status", "completion_date"])
        return assignment
