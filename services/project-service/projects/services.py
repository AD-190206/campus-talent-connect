
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Project


def create_project(*, client_id, **data):
    """Create a project owned by the specified client."""
    project = Project(
        client_id=client_id,
        **data,
    )
    project.full_clean()
    project.save()
    return project


def update_project(*, project, client_id, **data):
    """Update a project's editable fields, checking ownership."""
    if str(project.client_id) != str(client_id):
        raise ValidationError("You cannot modify another client's project.")

    if project.status in (
        Project.Status.CLOSED,
        Project.Status.ARCHIVED,
        Project.Status.COMPLETED,
    ):
        raise ValidationError("This project can no longer be edited.")

    allowed_fields = {
        "title",
        "description",
        "skills",
        "category",
        "budget",
        "deadline",
    }

    for field, value in data.items():
        if field in allowed_fields:
            setattr(project, field, value)

    project.full_clean()
    project.save()
    return project


def publish_project(*, project, client_id):
    """Publish a draft project."""
    if str(project.client_id) != str(client_id):
        raise ValidationError("You cannot publish another client's project.")

    if project.status != Project.Status.DRAFT:
        raise ValidationError("Only draft projects can be published.")

    project.status = Project.Status.PUBLISHED
    project.save(update_fields=["status", "updated_at"])
    return project


def close_project(*, project, client_id):
    """Close a project owned by the specified client."""
    if str(project.client_id) != str(client_id):
        raise ValidationError("You cannot close another client's project.")

    if project.status in (
        Project.Status.CLOSED,
        Project.Status.ARCHIVED,
        Project.Status.COMPLETED,
    ):
        raise ValidationError("This project is already finalized.")

    project.status = Project.Status.CLOSED
    project.save(update_fields=["status", "updated_at"])
    return project


def search_projects(*, query=None, skill=None, category=None,
                    max_budget=None):
    """Search published projects with optional filters."""
    projects = Project.objects.filter(
        status=Project.Status.PUBLISHED
    )

    if query:
        projects = projects.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
        )

    if skill:
        projects = [
            project
            for project in projects
            if any(
                skill.lower() in item.lower()
                for item in project.skills
            )
        ]

    if category:
        projects = (
            projects.filter(category__iexact=category)
            if hasattr(projects, "filter")
            else [
                project for project in projects
                if project.category.lower() == category.lower()
            ]
        )

    if max_budget is not None:
        projects = (
            projects.filter(budget__lte=max_budget)
            if hasattr(projects, "filter")
            else [
                project for project in projects
                if project.budget <= max_budget
            ]
        )

    return projects
