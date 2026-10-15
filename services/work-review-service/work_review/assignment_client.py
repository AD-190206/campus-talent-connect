import os

import requests


class AssignmentServiceError(Exception):
    """Base error for Assignment Service communication."""


class AssignmentNotFoundError(AssignmentServiceError):
    """The requested assignment does not exist."""


class AssignmentServiceUnavailableError(AssignmentServiceError):
    """The Assignment Service could not be reached or returned an error."""


def get_assignment(assignment_id):
    base_url = os.getenv("APPLICATION_SERVICE_URL", "").rstrip("/")

    if not base_url:
        raise AssignmentServiceUnavailableError(
            "Assignment Service URL is not configured."
        )

    url = f"{base_url}/api/assignments/{assignment_id}/"

    try:
        response = requests.get(url, timeout=3)
    except requests.RequestException as exc:
        raise AssignmentServiceUnavailableError(
            "Could not reach the Assignment Service."
        ) from exc

    if response.status_code == 404:
        raise AssignmentNotFoundError("Assignment not found.")

    if response.status_code != 200:
        raise AssignmentServiceUnavailableError(
            "Assignment Service returned an unexpected response."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise AssignmentServiceUnavailableError(
            "Assignment Service returned invalid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise AssignmentServiceUnavailableError(
            "Assignment Service returned an unexpected data format."
        )

    return data