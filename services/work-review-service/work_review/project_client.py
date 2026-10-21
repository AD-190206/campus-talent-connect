import os

import requests


class ProjectServiceError(Exception):
    """Base error for Project Service communication."""


class ProjectNotFoundError(ProjectServiceError):
    """The requested project does not exist."""


class ProjectAuthorizationError(ProjectServiceError):
    """The Project Service rejected the caller's authorization."""


class ProjectServiceUnavailableError(ProjectServiceError):
    """The Project Service could not be reached or returned invalid data."""


def get_project(project_id, access_token):
    base_url = os.getenv("PROJECT_SERVICE_URL", "").rstrip("/")

    if not base_url:
        raise ProjectServiceUnavailableError(
            "Project Service URL is not configured."
        )

    if not access_token:
        raise ProjectAuthorizationError(
            "A caller access token is required."
        )

    url = f"{base_url}/api/projects/{project_id}/"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(url, headers=headers, timeout=3)
    except requests.RequestException as exc:
        raise ProjectServiceUnavailableError(
            "Could not reach the Project Service."
        ) from exc

    if response.status_code == 404:
        raise ProjectNotFoundError("Project not found.")

    if response.status_code in (401, 403):
        raise ProjectAuthorizationError(
            "Project Service rejected the caller's authorization."
        )

    if response.status_code != 200:
        raise ProjectServiceUnavailableError(
            f"Project Service returned HTTP {response.status_code}."
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise ProjectServiceUnavailableError(
            "Project Service returned invalid JSON."
        ) from exc

    if not isinstance(body, dict):
        raise ProjectServiceUnavailableError(
            "Project Service returned an unexpected response format."
        )

    data = body.get("data")
    if not isinstance(data, dict):
        raise ProjectServiceUnavailableError(
            "Project Service returned an invalid response envelope."
        )

    if not data.get("client_id") or data.get("budget") is None:
        raise ProjectServiceUnavailableError(
            "Project response is missing ownership or budget information."
        )

    return data
