
from decimal import Decimal, InvalidOperation

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
    """Update a project's editable fields after checking ownership."""
    if str(project.client_id) != str(client_id):
        raise ValidationError(
            "You cannot modify another client's project."
        )

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
    """Publish a draft project after checking ownership."""
    if str(project.client_id) != str(client_id):
        raise ValidationError(
            "You cannot publish another client's project."
        )

    if project.status != Project.Status.DRAFT:
        raise ValidationError(
            "Only draft projects can be published."
        )

    project.status = Project.Status.PUBLISHED
    project.save(update_fields=["status", "updated_at"])
    return project


def close_project(*, project, client_id):
    """Close a project owned by the specified client."""
    if str(project.client_id) != str(client_id):
        raise ValidationError(
            "You cannot close another client's project."
        )

    if project.status in (
        Project.Status.CLOSED,
        Project.Status.ARCHIVED,
        Project.Status.COMPLETED,
    ):
        raise ValidationError(
            "This project is already finalized."
        )

    project.status = Project.Status.CLOSED
    project.save(update_fields=["status", "updated_at"])
    return project


def search_projects(
    *,
    query=None,
    skill=None,
    category=None,
    max_budget=None,
):
    """Search published projects using optional filters."""
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

    if skill:
        skill = skill.strip()
        if skill:
            # JSONField stores skills as a list of strings.
            # Use a database-level containment lookup where supported.
            # Fall back to case-insensitive Python filtering on databases
            # that don't support this JSONField lookup.
            try:
                projects = projects.filter(
                    skills__icontains=skill
                )
            except (NotImplementedError, ValueError):
                projects = [
                    project
                    for project in projects
                    if any(
                        skill.lower() in item.lower()
                        for item in project.skills
                        if isinstance(item, str)
                    )
                ]

    if category:
        projects = (
            projects.filter(category__iexact=category.strip())
            if hasattr(projects, "filter")
            else [
                project
                for project in projects
                if project.category.lower() == category.strip().lower()
            ]
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
                "Maximum budget must be a non-negative number."
            )

        projects = (
            projects.filter(budget__lte=max_budget)
            if hasattr(projects, "filter")
            else [
                project
                for project in projects
                if project.budget <= max_budget
            ]
        )

    return projects
