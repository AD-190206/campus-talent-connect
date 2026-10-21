
import requests
from django.conf import settings


class UpstreamServiceError(Exception):
    """Represents a failed or invalid upstream service response."""

    def __init__(self, message, code, http_status):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def get_upstream_data(base_url, path, authorization):
    """
    Perform an authenticated GET request to another CTC service.

    Successful responses must use the shared API envelope:
    {"data": ..., "message": "..."}
    """
    if not base_url:
        raise UpstreamServiceError(
            "The required upstream service is not configured.",
            "UPSTREAM_NOT_CONFIGURED",
            503,
        )

    if not authorization:
        raise UpstreamServiceError(
            "The caller's authorization token is missing.",
            "UPSTREAM_AUTHORIZATION_MISSING",
            401,
        )

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    try:
        response = requests.get(
            url,
            headers={"Authorization": authorization},
            timeout=(
                settings.UPSTREAM_CONNECT_TIMEOUT,
                settings.UPSTREAM_READ_TIMEOUT,
            ),
        )
    except requests.Timeout as exc:
        raise UpstreamServiceError(
            "The upstream service timed out.",
            "UPSTREAM_TIMEOUT",
            504,
        ) from exc
    except requests.RequestException as exc:
        raise UpstreamServiceError(
            "The upstream service is unavailable.",
            "UPSTREAM_UNAVAILABLE",
            503,
        ) from exc

    # Distinguish a missing resource from an unavailable dependency.
    if response.status_code == 404:
        raise UpstreamServiceError(
            "The requested upstream resource was not found.",
            "UPSTREAM_RESOURCE_NOT_FOUND",
            404,
        )

    if response.status_code in (401, 403):
        raise UpstreamServiceError(
            "The upstream service rejected authorization.",
            "UPSTREAM_AUTHORIZATION_FAILED",
            502,
        )

    if not response.ok:
        raise UpstreamServiceError(
            "The upstream service returned an unsuccessful response.",
            "UPSTREAM_REQUEST_FAILED",
            502,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise UpstreamServiceError(
            "The upstream service returned invalid JSON.",
            "UPSTREAM_INVALID_RESPONSE",
            502,
        ) from exc

    if (
        not isinstance(payload, dict)
        or "data" not in payload
        or not isinstance(payload.get("message"), str)
    ):
        raise UpstreamServiceError(
            "The upstream response does not match the API contract.",
            "UPSTREAM_INVALID_RESPONSE",
            502,
        )

    return payload["data"]


def get_assignment(assignment_id, authorization):
    """Fetch an assignment from the Application Service."""
    return get_upstream_data(
        settings.APPLICATION_SERVICE_URL,
        f"/api/assignments/{assignment_id}/",
        authorization,
    )


def get_project(project_id, authorization):
    """Fetch a project from the Project Service."""
    return get_upstream_data(
        settings.PROJECT_SERVICE_URL,
        f"/api/projects/{project_id}/",
        authorization,
    )
