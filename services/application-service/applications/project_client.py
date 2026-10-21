"""REST client for the Project service.

Every call forwards the initiating user's bearer token (contract §5.3), so the
Project service authorizes the call independently.
"""
import os

import requests

from .api import ApiError

PROJECT_SERVICE_URL = os.getenv(
    "PROJECT_SERVICE_URL", "http://project-service:8002"
).rstrip("/")

# (connect, read) timeouts in seconds.
TIMEOUT = (3, 5)


def _request(method, path, auth_header):
    url = f"{PROJECT_SERVICE_URL}{path}"
    try:
        resp = requests.request(
            method,
            url,
            headers={"Authorization": auth_header},
            json={} if method == "POST" else None,
            timeout=TIMEOUT,
        )
    except requests.Timeout:
        raise ApiError(
            "Project service timed out.", "UPSTREAM_SERVICE_ERROR", 504
        )
    except requests.RequestException:
        raise ApiError(
            "Project service is unavailable.", "UPSTREAM_SERVICE_ERROR", 503
        )

    try:
        body = resp.json()
    except ValueError:
        body = None

    if resp.status_code == 404:
        raise ApiError("Project not found.", "NOT_FOUND", 404)

    if resp.status_code == 403:
        raise ApiError("Project is not accessible.", "FORBIDDEN", 403)

    if resp.status_code == 400 and isinstance(body, dict):
        # Lifecycle errors from the project service are meaningful to callers.
        raise ApiError(
            body.get("error") or "Project service rejected the request.",
            body.get("code") or "INVALID_STATE_TRANSITION",
            400,
        )

    if resp.status_code != 200 or not isinstance(body, dict) or not isinstance(
        body.get("data"), dict
    ):
        raise ApiError(
            "Unexpected response from project service.",
            "UPSTREAM_SERVICE_ERROR",
            502,
        )

    return body["data"]


def get_project(project_id, auth_header):
    """Fetch a project the caller is allowed to see."""
    return _request("GET", f"/api/projects/{project_id}/", auth_header)


def start_project(project_id, auth_header):
    """Move the project to IN_PROGRESS (idempotent on the project side)."""
    return _request("POST", f"/api/projects/{project_id}/start/", auth_header)
