from django.shortcuts import get_object_or_404
from .models import Application, Assignment, ApplicationStatus, AssignmentStatus


class DuplicateApplicationError(Exception):
    """Raised when a student tries to apply to the same project twice."""
    pass


def get_applications_for_project(project_id):
    """Return all applications for a given project. Called by business."""
    return Application.objects.filter(project_id=project_id)


def get_applications_for_student(student_id):
    """Return all applications made by a student."""
    return Application.objects.filter(student_id=student_id)


def get_application_by_id(application_id):
    """Fetch a single application or 404."""
    return get_object_or_404(Application, id=application_id)


def create_application(student_id, project_id, proposal, resume_url=""):
    """
    Create a new application.
    Raises DuplicateApplicationError if student already applied to this project.
    """
    if Application.objects.filter(student_id=student_id, project_id=project_id).exists():
        raise DuplicateApplicationError()

    return Application.objects.create(
        student_id=student_id,
        project_id=project_id,
        proposal=proposal,
        resume_url=resume_url,
        status=ApplicationStatus.SUBMITTED,
    )


def update_application(application_id, proposal=None, resume_url=None):
    """Full update of proposal and resume_url. Used by PUT endpoint."""
    application = get_object_or_404(Application, id=application_id)

    if proposal is not None:
        application.proposal = proposal
    if resume_url is not None:
        application.resume_url = resume_url

    application.save()
    return application


def shortlist_application(application_id):
    """Business shortlists an application."""
    application = get_object_or_404(Application, id=application_id)
    application.status = ApplicationStatus.SHORTLISTED
    application.save()
    return application


def select_application(application_id):
    """
    Business selects a student.
    Automatically creates an Assignment.
    """
    application = get_object_or_404(Application, id=application_id)
    application.status = ApplicationStatus.SELECTED
    application.save()

    assignment = _create_assignment(application)
    return application, assignment


def reject_application(application_id):
    """Business rejects an application."""
    application = get_object_or_404(Application, id=application_id)
    application.status = ApplicationStatus.REJECTED
    application.save()
    return application


def withdraw_application(application_id):
    """Student withdraws their own application."""
    application = get_object_or_404(Application, id=application_id)
    terminal = [ApplicationStatus.SELECTED, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN]

    if application.status in terminal:
        raise ValueError(f"Cannot withdraw an application with status '{application.status}'.")

    application.status = ApplicationStatus.WITHDRAWN
    application.save()
    return application


def _create_assignment(application):
    """
    Internal — creates Assignment from a selected Application.
    Uses get_or_create to prevent duplicates if called twice.
    """
    assignment, _ = Assignment.objects.get_or_create(
        application_id=application.id,
        defaults={
            "student_id": application.student_id,
            "project_id": application.project_id,
            "status":     AssignmentStatus.ACTIVE,
        }
    )
    return assignment


def get_assignment_by_id(assignment_id):
    """Fetch a single assignment or 404. Used by Person 4 and Person 5."""
    return get_object_or_404(Assignment, id=assignment_id)


def get_assignments_for_project(project_id):
    return Assignment.objects.filter(project_id=project_id)


def get_all_assignments():
    """Return all assignments."""
    return Assignment.objects.all()