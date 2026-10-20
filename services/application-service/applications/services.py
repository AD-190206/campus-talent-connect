from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Application, Assignment, ApplicationStatus, AssignmentStatus


class DuplicateApplicationError(Exception):
    pass


def create_application(student_id, project_id, proposal, resume_url=""):
    if Application.objects.filter(student_id=student_id, project_id=project_id).exists():
        raise DuplicateApplicationError()
    return Application.objects.create(
        student_id=student_id,
        project_id=project_id,
        proposal=proposal,
        resume_url=resume_url,
        status=ApplicationStatus.SUBMITTED,
    )


def get_applications_for_project(project_id):
    return Application.objects.filter(project_id=project_id)


def get_applications_for_student(student_id):
    return Application.objects.filter(student_id=student_id)


def get_application_by_id(application_id):
    return get_object_or_404(Application, id=application_id)


def shortlist_application(application_id):
    application = get_object_or_404(Application, id=application_id)
    if application.status != ApplicationStatus.SUBMITTED:
        raise ValueError(
            f"Cannot shortlist application with status '{application.status}'. "
            f"Only 'submitted' applications can be shortlisted."
        )
    application.status = ApplicationStatus.SHORTLISTED
    application.save()
    return application


def select_application(application_id, client_id=None):
    with transaction.atomic():
        application = get_object_or_404(Application, id=application_id)
        if application.status != ApplicationStatus.SHORTLISTED:
            raise ValueError(
                f"Cannot select application with status '{application.status}'. "
                f"Only 'shortlisted' applications can be selected."
            )
        application.status = ApplicationStatus.SELECTED
        application.save()
        assignment = _create_assignment(application, client_id=client_id)
    return application, assignment


def reject_application(application_id):
    application = get_object_or_404(Application, id=application_id)
    allowed = [ApplicationStatus.SUBMITTED, ApplicationStatus.SHORTLISTED]
    if application.status not in allowed:
        raise ValueError(
            f"Cannot reject application with status '{application.status}'. "
            f"Only 'submitted' or 'shortlisted' applications can be rejected."
        )
    application.status = ApplicationStatus.REJECTED
    application.save()
    return application


def withdraw_application(application_id):
    application = get_object_or_404(Application, id=application_id)
    terminal = [
        ApplicationStatus.SELECTED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ]
    if application.status in terminal:
        raise ValueError(
            f"Cannot withdraw an application with status '{application.status}'."
        )
    application.status = ApplicationStatus.WITHDRAWN
    application.save()
    return application


def _create_assignment(application, client_id=0):
    assignment, _ = Assignment.objects.get_or_create(
        application_id=application.id,
        defaults={
            "student_id": application.student_id,
            "client_id": client_id,
            "project_id": application.project_id,
            "status": AssignmentStatus.ACTIVE,
        },
    )
    return assignment


def update_application(application_id, proposal=None, resume_url=None):
    application = get_object_or_404(Application, id=application_id)
    if proposal is not None:
        application.proposal = proposal
    if resume_url is not None:
        application.resume_url = resume_url
    application.save()
    return application


def get_all_assignments():
    return Assignment.objects.all()


def get_assignment_by_id(assignment_id):
    return get_object_or_404(Assignment, id=assignment_id)


def get_assignments_for_project(project_id):
    return Assignment.objects.filter(project_id=project_id)
