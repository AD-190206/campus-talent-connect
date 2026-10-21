from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from .models import Project

Status = Project.Status

# Lifecycle rules. The service layer is the only place that changes status.
#
# PUBLISHED -> IN_PROGRESS happens when the Application service assigns a
# student (start/), and IN_PROGRESS -> COMPLETED when Work & Review approves
# the deliverable (complete/). Both calls forward the owning client's token.
# ARCHIVED is reserved; nothing moves a project there in this iteration.
ALLOWED_TRANSITIONS = {
    Status.DRAFT: {Status.PUBLISHED, Status.CLOSED},
    Status.PUBLISHED: {Status.IN_PROGRESS, Status.CLOSED},
    Status.IN_PROGRESS: {Status.COMPLETED, Status.CLOSED},
    Status.COMPLETED: set(),
    Status.CLOSED: set(),
    Status.ARCHIVED: set(),
}

# Statuses in which a client may still edit a project. The budget is the
# source of truth for payments, so it is frozen once work has started.
EDITABLE_STATUSES = {Status.DRAFT, Status.PUBLISHED}

# Statuses in which a project may be deleted. Projects that other services
# may reference (published, in progress, completed) cannot be deleted.
DELETABLE_STATUSES = {Status.DRAFT, Status.CLOSED, Status.ARCHIVED}


class NotProjectOwner(ValidationError):
    """Raised when someone acts on a project they do not own.

    Subclasses ValidationError so existing callers still work; the API layer
    turns it into 403 FORBIDDEN.
    """


class InvalidStateTransition(ValidationError):
    """Raised when the project's current status does not allow an action.

    The API layer turns it into 400 INVALID_STATE_TRANSITION.
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


def _check_transition(project, target, message):
    if target not in ALLOWED_TRANSITIONS[project.status]:
        raise InvalidStateTransition(message)


def update_project(*, project, client_id, **data):
    """Update editable fields of a client's own project."""
    _check_owner(project, client_id)

    if project.status not in EDITABLE_STATUSES:
        raise InvalidStateTransition(
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
    _check_transition(
        project, Status.PUBLISHED, "Only draft projects can be published."
    )

    if project.deadline < timezone.localdate():
        raise ValidationError(
            {"deadline": "A project with a past deadline cannot be published."}
        )

    project.status = Status.PUBLISHED
    project.full_clean()
    project.save(update_fields=["status", "updated_at"])
    return project


def start_project(*, project, client_id):
    """Mark a published project as in progress. Repeating it is a no-op."""
    _check_owner(project, client_id)

    if project.status == Status.IN_PROGRESS:
        return project

    _check_transition(
        project,
        Status.IN_PROGRESS,
        "Only published projects can be started.",
    )

    project.status = Status.IN_PROGRESS
    project.save(update_fields=["status", "updated_at"])
    return project


def complete_project(*, project, client_id):
    """Mark an in-progress project as completed. Repeating it is a no-op."""
    _check_owner(project, client_id)

    if project.status == Status.COMPLETED:
        return project

    _check_transition(
        project,
        Status.COMPLETED,
        "Only in-progress projects can be completed.",
    )

    project.status = Status.COMPLETED
    project.save(update_fields=["status", "updated_at"])
    return project


def close_project(*, project, client_id, acting_as_admin=False):
    """Close a project. Owners and admins may close it."""
    if not acting_as_admin:
        _check_owner(project, client_id)

    _check_transition(
        project,
        Status.CLOSED,
        "This project cannot be closed in its current status.",
    )

    project.status = Status.CLOSED
    project.full_clean()
    project.save(update_fields=["status", "updated_at"])
    return project


def delete_project(*, project):
    """Delete a project if its status allows it."""
    if project.status not in DELETABLE_STATUSES:
        raise InvalidStateTransition(
            "Projects in this status cannot be deleted."
        )

    project.delete()


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
        else Project.objects.filter(status=Status.PUBLISHED)
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
            raise ValidationError(
                {"max_budget": "Maximum budget must be a valid number."}
            )

        if not max_budget.is_finite() or max_budget < 0:
            raise ValidationError(
                {
                    "max_budget": (
                        "Maximum budget must be a finite, "
                        "non-negative number."
                    )
                }
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