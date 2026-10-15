from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Project


class NotProjectOwner(ValidationError):
    """Raised when a client tries to act on a project they do not own.

    Subclasses ValidationError so existing callers still work; the views
    catch it first and return 403.
    """


def create_project(*, client_id, **data):
    """Create a new project owned by the specified client."""
    project = Project(client_id=client_id, **data)
    project.full_clean()
    project.save()
    return project


def _check_owner(project, client_id):
    if str(project.client_id) != str(client_id):
        raise NotProjectOwner(
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
    _check_owner(project, client_id)

    if project.status != Project.Status.DRAFT:
        raise ValidationError("Only draft projects can be published.")

    if project.deadline < date.today():
        raise ValidationError(
            "A project with a past deadline cannot be published."
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
    queryset=None,
    query=None,
    skill=None,
    category=None,
    max_budget=None,
):
    """
    Filter projects by text, skill, category and maximum budget.

    `queryset` is the set of projects the caller is allowed to see.
    When omitted, only PUBLISHED projects are searched.

    Skills live in a JSONField, so matching is done in Python and the
    result is turned back into a queryset via primary keys. This avoids
    database-specific JSON lookups.
    """
    projects = (
        queryset
        if queryset is not None
        else Project.objects.filter(status=Project.Status.PUBLISHED)
    )

    if query and query.strip():
        query = query.strip()
        projects = projects.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )

    if category and category.strip():
        projects = projects.filter(category__iexact=category.strip())

    if max_budget is not None:
        try:
            max_budget = Decimal(str(max_budget))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError("Maximum budget must be a valid number.")

        if not max_budget.is_finite() or max_budget < 0:
            raise ValidationError(
                "Maximum budget must be a finite, non-negative number."
            )

        projects = projects.filter(budget__lte=max_budget)

    if skill and skill.strip():
        skill = skill.strip().lower()
        matching_ids = [
            project.pk
            for project in projects
            if isinstance(project.skills, list)
            and any(
                isinstance(item, str) and skill in item.lower()
                for item in project.skills
            )
        ]
        projects = projects.filter(pk__in=matching_ids)

    return projects
