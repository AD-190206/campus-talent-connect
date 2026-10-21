import os

import requests


class AssignmentServiceError(Exception):
    """Base error for Assignment Service communication."""


class AssignmentNotFoundError(AssignmentServiceError):
    """The requested assignment does not exist."""


class AssignmentAuthorizationError(AssignmentServiceError):
    """The caller is not authorized to access the assignment."""


class AssignmentServiceUnavailableError(AssignmentServiceError):
    """The Assignment Service could not be reached or returned an error."""


def get_assignment(assignment_id, access_token):
    base_url = os.getenv("APPLICATION_SERVICE_URL", "").rstrip("/")

    if not base_url:
        raise AssignmentServiceUnavailableError(
            "Assignment Service URL is not configured."
        )

    if not access_token:
        raise AssignmentAuthorizationError(
            "A caller access token is required."
        )

    url = f"{base_url}/api/assignments/{assignment_id}/"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(url, headers=headers, timeout=3)
    except requests.RequestException as exc:
        raise AssignmentServiceUnavailableError(
            "Could not reach the Assignment Service."
        ) from exc

    if response.status_code == 404:
        raise AssignmentNotFoundError("Assignment not found.")

    if response.status_code in (401, 403):
        raise AssignmentAuthorizationError(
            "Assignment Service rejected the caller's authorization."
        )

    if response.status_code != 200:
        raise AssignmentServiceUnavailableError(
            "Assignment Service returned an unexpected response."
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise AssignmentServiceUnavailableError(
            "Assignment Service returned invalid JSON."
        ) from exc

    if not isinstance(body, dict):
        raise AssignmentServiceUnavailableError(
            "Assignment Service returned an unexpected data format."
        )

    # The shared contract wraps successful responses in {"data": ..., "message": ...}.
    data = body.get("data")
    if not isinstance(data, dict):
        raise AssignmentServiceUnavailableError(
            "Assignment Service returned an invalid response envelope."
        )

    return data


def complete_assignment(assignment_id, access_token):
    """Mark the assignment completed (idempotent on the Application side)."""
    base_url = os.getenv("APPLICATION_SERVICE_URL", "").rstrip("/")

    if not base_url:
        raise AssignmentServiceUnavailableError(
            "Assignment Service URL is not configured."
        )

    if not access_token:
        raise AssignmentAuthorizationError(
            "A caller access token is required."
        )

    url = f"{base_url}/api/assignments/{assignment_id}/complete/"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.post(url, json={}, headers=headers, timeout=3)
    except requests.RequestException as exc:
        raise AssignmentServiceUnavailableError(
            "Could not reach the Assignment Service."
        ) from exc

    if response.status_code == 404:
        raise AssignmentNotFoundError("Assignment not found.")

    if response.status_code in (401, 403):
        raise AssignmentAuthorizationError(
            "Assignment Service rejected the caller's authorization."
        )

    if response.status_code != 200:
        raise AssignmentServiceUnavailableError(
            f"Assignment Service returned HTTP {response.status_code}."
        )

    return response.json().get("data")
