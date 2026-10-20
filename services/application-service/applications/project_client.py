import os
import requests
from rest_framework import status
from rest_framework.response import Response


PROJECT_SERVICE_URL = os.getenv("PROJECT_SERVICE_URL", "http://project-service:8002")


class ProjectServiceError(Exception):
    def __init__(self, message, code, http_status):
        self.message = message
        self.code = code
        self.http_status = http_status
        super().__init__(message)


def get_project(project_id, auth_header):
    """
    Fetch project from project-service.
    Returns project data dict on success.
    Raises ProjectServiceError on any failure.
    """
    url = f"{PROJECT_SERVICE_URL}/api/projects/{project_id}/"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": auth_header},
            timeout=5,
        )
    except requests.Timeout:
        raise ProjectServiceError(
            "Project service timed out.",
            "UPSTREAM_SERVICE_ERROR",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except requests.ConnectionError:
        raise ProjectServiceError(
            "Project service is unavailable.",
            "UPSTREAM_SERVICE_ERROR",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if resp.status_code == 404:
        raise ProjectServiceError(
            "Project not found.",
            "NOT_FOUND",
            status.HTTP_404_NOT_FOUND,
        )
    if resp.status_code == 403:
        raise ProjectServiceError(
            "Project is not accessible.",
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
        )
    if resp.status_code != 200:
        raise ProjectServiceError(
            "Unexpected error from project service.",
            "UPSTREAM_SERVICE_ERROR",
            status.HTTP_502_BAD_GATEWAY,
        )

    return resp.json()["data"]


def update_project_status(project_id, new_status, auth_header):
    url = f"{PROJECT_SERVICE_URL}/api/projects/{project_id}/status/"
    try:
        resp = requests.patch(
            url,
            json={"status": new_status},
            headers={"Authorization": auth_header},
            timeout=5,
        )
    except requests.Timeout:
        raise ProjectServiceError("Project service timed out.", "UPSTREAM_SERVICE_ERROR", 503)
    except requests.ConnectionError:
        raise ProjectServiceError("Project service unavailable.", "UPSTREAM_SERVICE_ERROR", 503)
    if resp.status_code not in (200, 204):
        raise ProjectServiceError("Failed to update project status.", "UPSTREAM_SERVICE_ERROR", 502)
