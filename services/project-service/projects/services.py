
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Project


def create_project(*, client_id, **data):
    """Create a new project owned by the specified client."""
    project = Project(client_id=client_id, **data)
    project.full_clean()
    project.save()
    return project


def _check_owner(project, client_id):
    if str(project.client_id) != str(client_id):
        raise ValidationError(
            "You cannot modify another client's project."
        )


def update_project(*, project, client_id, **data):
    """Update editable fields of a client's own project."""
    _check_owner(project, client_id)

    if project.status in (
        Project.Status.CLOSED,
        Project.Status.ARCHIVED,
        Project.Status.COMPLETED,
    ):
        raise ValidationError(
            "This project can no longer be edited."
        )

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
    _check_owner(project, client_id)

    if project.status != Project.Status.DRAFT:
        raise ValidationError(
            "Only draft projects can be published."
        )

    project.status = Project.Status.PUBLISHED
    project.full_clean()
    project.save(update_fields=["status", "updated_at"])
    return project


def close_project(*, project, client_id):
    """Close a client's own project."""
    _check_owner(project, client_id)

    if project.status in (
        Project.Status.CLOSED,
        Project.Status.ARCHIVED,
        Project.Status.COMPLETED,
    ):
        raise ValidationError(
            "This project cannot be closed in its current status."
        )

    project.status = Project.Status.CLOSED
    project.full_clean()
    project.save(update_fields=["status", "updated_at"])
    return project


def search_projects(
    *,
    query=None,
    skill=None,
    category=None,
    max_budget=None,
):
    """
    Search published projects by text, skill, category, and budget.

    Skills are stored in a JSONField. Skill matching is performed in
    Python to avoid database-specific JSON text lookup behaviour.
    """
    projects = Project.objects.filter(
        status=Project.Status.PUBLISHED
    )

    if query:
        query = query.strip()
        if query:
            projects = projects.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
            )

    if category:
        category = category.strip()
        if category:
            projects = projects.filter(
                category__iexact=category
            )

    if max_budget is not None:
        try:
            max_budget = Decimal(str(max_budget))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(
                "Maximum budget must be a valid number."
            )

        if not max_budget.is_finite() or max_budget < 0:
            raise ValidationError(
                "Maximum budget must be a finite, non-negative number."
            )

        projects = projects.filter(budget__lte=max_budget)

    if skill:
        skill = skill.strip().lower()
        if skill:
            projects = [
                project
                for project in projects
                if isinstance(project.skills, list)
                and any(
                    isinstance(item, str)
                    and skill in item.lower()
                    for item in project.skills
                )
            ]

    return projects
