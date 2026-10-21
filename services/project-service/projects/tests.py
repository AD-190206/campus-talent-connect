from datetime import date, timedelta
from decimal import Decimal
import time
import uuid
from unittest import mock

import jwt
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from rest_framework.test import APIClient

from .models import Project
from .services import (
    InvalidStateTransition,
    NotProjectOwner,
    close_project,
    create_project,
    delete_project,
    publish_project,
    search_projects,
    update_project,
)


# ===================================================== service-layer tests

class ProjectServiceTests(TestCase):
    def setUp(self):
        self.client_id = uuid.uuid4()
        self.other_client_id = uuid.uuid4()

        self.project = create_project(
            client_id=self.client_id,
            title="Build a Django API",
            description="Develop a REST API for a student project.",
            skills=["Python", "Django", "REST"],
            category="Software",
            budget=Decimal("15000.00"),
            deadline=date.today() + timedelta(days=30),
        )

    def test_project_is_created_as_draft(self):
        self.assertEqual(self.project.status, Project.Status.DRAFT)
        self.assertEqual(self.project.client_id, self.client_id)

    def test_project_can_be_published(self):
        publish_project(project=self.project, client_id=self.client_id)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.PUBLISHED)

    def test_only_owner_can_publish_project(self):
        with self.assertRaises(ValidationError):
            publish_project(
                project=self.project, client_id=self.other_client_id
            )

    def test_non_owner_error_is_ownership_error(self):
        with self.assertRaises(NotProjectOwner):
            publish_project(
                project=self.project, client_id=self.other_client_id
            )

    def test_published_project_can_be_closed(self):
        publish_project(project=self.project, client_id=self.client_id)
        close_project(project=self.project, client_id=self.client_id)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.CLOSED)

    def test_admin_can_close_any_project(self):
        close_project(
            project=self.project,
            client_id=self.other_client_id,
            acting_as_admin=True,
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.CLOSED)

    def test_publishing_twice_is_invalid_transition(self):
        publish_project(project=self.project, client_id=self.client_id)
        with self.assertRaises(InvalidStateTransition):
            publish_project(project=self.project, client_id=self.client_id)

    def test_closing_twice_is_invalid_transition(self):
        close_project(project=self.project, client_id=self.client_id)
        with self.assertRaises(InvalidStateTransition):
            close_project(project=self.project, client_id=self.client_id)

    def test_owner_can_update_project(self):
        updated = update_project(
            project=self.project,
            client_id=self.client_id,
            title="Updated Django API",
        )
        self.assertEqual(updated.title, "Updated Django API")

    def test_other_client_cannot_update_project(self):
        with self.assertRaises(ValidationError):
            update_project(
                project=self.project,
                client_id=self.other_client_id,
                title="Unauthorized change",
            )

    def test_closed_project_cannot_be_edited(self):
        close_project(project=self.project, client_id=self.client_id)
        with self.assertRaises(InvalidStateTransition):
            update_project(
                project=self.project,
                client_id=self.client_id,
                title="Too late",
            )

    def test_in_progress_project_cannot_be_edited(self):
        Project.objects.filter(pk=self.project.pk).update(
            status=Project.Status.IN_PROGRESS
        )
        self.project.refresh_from_db()
        with self.assertRaises(InvalidStateTransition):
            update_project(
                project=self.project,
                client_id=self.client_id,
                budget=Decimal("99999.00"),
            )

    def test_past_deadline_project_cannot_be_published(self):
        Project.objects.filter(pk=self.project.pk).update(
            deadline=date.today() - timedelta(days=1)
        )
        self.project.refresh_from_db()
        with self.assertRaises(ValidationError):
            publish_project(project=self.project, client_id=self.client_id)

    def test_budget_must_be_positive(self):
        with self.assertRaises(ValidationError):
            create_project(
                client_id=self.client_id,
                title="Invalid budget project",
                description="This project has an invalid budget.",
                skills=["Python"],
                category="Software",
                budget=Decimal("0.00"),
                deadline=date.today() + timedelta(days=10),
            )

    def test_draft_can_be_deleted(self):
        delete_project(project=self.project)
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())

    def test_published_project_cannot_be_deleted(self):
        publish_project(project=self.project, client_id=self.client_id)
        with self.assertRaises(InvalidStateTransition):
            delete_project(project=self.project)

    def test_search_returns_published_projects(self):
        publish_project(project=self.project, client_id=self.client_id)
        results = search_projects(query="Django")
        self.assertIn(self.project, results)

    def test_search_excludes_draft_projects(self):
        results = search_projects(query="Django")
        self.assertNotIn(self.project, results)

    def test_search_filters_by_skill(self):
        publish_project(project=self.project, client_id=self.client_id)
        results = search_projects(skill="python")
        self.assertIn(self.project, results)
        results = search_projects(skill="rust")
        self.assertNotIn(self.project, results)

    def test_search_filters_by_category(self):
        publish_project(project=self.project, client_id=self.client_id)
        self.assertIn(self.project, search_projects(category="software"))
        self.assertNotIn(self.project, search_projects(category="design"))

    def test_search_filters_by_maximum_budget(self):
        publish_project(project=self.project, client_id=self.client_id)

        results = search_projects(max_budget="20000")
        self.assertIn(self.project, results)

        results = search_projects(max_budget="10000")
        self.assertNotIn(self.project, results)

    def test_search_rejects_invalid_budget(self):
        with self.assertRaises(ValidationError):
            search_projects(max_budget="abc")


# ======================================================== API test helpers

class FakeUser:
    """Stand-in for the user built from a verified token."""

    is_authenticated = True
    is_staff = False
    is_superuser = False

    def __init__(self, role, user_id=None):
        self.role = role
        self.id = user_id or uuid.uuid4()


def make_token(
    role="CLIENT",
    user_id=None,
    token_type="access",
    exp_delta=1800,
    secret=None,
    algorithm="HS256",
    drop=(),
    **extra,
):
    """Build a signed JWT shaped like the User service's tokens."""
    if user_id is None:
        user_id = uuid.uuid4()

    now = int(time.time())
    payload = {
        "user_id": str(user_id) if isinstance(user_id, uuid.UUID) else user_id,
        "role": role,
        "token_type": token_type,
        "iat": now,
        "exp": now + exp_delta,
    }
    payload.update(extra)
    for claim in drop:
        payload.pop(claim, None)

    return jwt.encode(
        payload,
        secret or settings.JWT_SECRET_KEY,
        algorithm=algorithm,
    )


def project_payload(**overrides):
    payload = {
        "title": "Build a Django API",
        "description": "Develop a REST API for a student project.",
        "skills": ["Python", "Django"],
        "category": "Software",
        "budget": "15000.00",
        "deadline": (date.today() + timedelta(days=30)).isoformat(),
    }
    payload.update(overrides)
    return payload


class ApiTestCase(TestCase):
    """Shared helpers for the endpoint tests."""

    def setUp(self):
        self.api = APIClient()
        self.owner = FakeUser("CLIENT")
        self.other_client = FakeUser("CLIENT")
        self.student = FakeUser("STUDENT")
        self.admin = FakeUser("ADMIN")

    def as_user(self, user):
        self.api.force_authenticate(user=user)

    def assertSuccess(self, response, status_code=200):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertIn("data", response.data)
        self.assertTrue(response.data["message"])

    def assertError(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code, response.data)
        self.assertEqual(response.data["code"], code)
        self.assertTrue(response.data["error"])
        self.assertIsInstance(response.data["details"], dict)

    def create_project(self, owner=None, **overrides):
        self.as_user(owner or self.owner)
        response = self.api.post(
            reverse("project-list-create"), project_payload(**overrides)
        )
        self.assertSuccess(response, 201)
        return response.data["data"]["id"]

    def publish(self, project_id, owner=None):
        self.as_user(owner or self.owner)
        response = self.api.post(
            reverse("project-publish", kwargs={"project_id": project_id})
        )
        self.assertSuccess(response)
        return response

    def detail_url(self, project_id):
        return reverse("project-detail", kwargs={"project_id": project_id})


# ============================================================ envelope tests

class ResponseEnvelopeTests(ApiTestCase):
    def test_create_returns_201_with_data_and_message(self):
        self.as_user(self.owner)
        response = self.api.post(
            reverse("project-list-create"), project_payload()
        )
        self.assertSuccess(response, 201)
        data = response.data["data"]
        self.assertEqual(data["status"], "DRAFT")
        self.assertEqual(data["client_id"], str(self.owner.id))
        self.assertEqual(data["budget"], "15000.00")

    def test_timestamps_are_utc_iso_strings(self):
        project_id = self.create_project()
        response = self.api.get(self.detail_url(project_id))
        self.assertTrue(response.data["data"]["created_at"].endswith("Z"))

    def test_list_has_pagination_envelope(self):
        self.create_project()
        response = self.api.get(reverse("project-list-create"))
        self.assertSuccess(response)
        self.assertIsInstance(response.data["data"], list)
        self.assertEqual(
            response.data["pagination"],
            {"page": 1, "page_size": 20, "total": 1, "total_pages": 1},
        )

    def test_validation_error_uses_error_envelope(self):
        self.as_user(self.owner)
        response = self.api.post(
            reverse("project-list-create"), project_payload(budget="0")
        )
        self.assertError(response, 400, "VALIDATION_ERROR")
        self.assertIn("budget", response.data["details"]["fields"])

    def test_missing_fields_are_listed_in_details(self):
        self.as_user(self.owner)
        response = self.api.post(reverse("project-list-create"), {})
        self.assertError(response, 400, "VALIDATION_ERROR")
        fields = response.data["details"]["fields"]
        for name in ("title", "description", "budget", "deadline"):
            self.assertIn(name, fields)

    def test_unknown_and_read_only_fields_are_rejected(self):
        self.as_user(self.owner)
        response = self.api.post(
            reverse("project-list-create"),
            project_payload(
                status="PUBLISHED", client_id=str(uuid.uuid4()), colour="red"
            ),
        )
        self.assertError(response, 400, "VALIDATION_ERROR")
        fields = response.data["details"]["fields"]
        for name in ("status", "client_id", "colour"):
            self.assertIn(name, fields)
        self.assertEqual(Project.objects.count(), 0)

    def test_malformed_json_uses_error_envelope(self):
        self.as_user(self.owner)
        response = self.api.post(
            reverse("project-list-create"),
            data="{not json",
            content_type="application/json",
        )
        self.assertError(response, 400, "VALIDATION_ERROR")

    def test_non_json_content_type_is_rejected(self):
        self.as_user(self.owner)
        response = self.api.post(
            reverse("project-list-create"),
            data="title=x",
            content_type="text/plain",
        )
        self.assertError(response, 415, "UNSUPPORTED_MEDIA_TYPE")

    def test_missing_project_is_json_404(self):
        self.as_user(self.owner)
        response = self.api.get(self.detail_url(uuid.uuid4()))
        self.assertError(response, 404, "NOT_FOUND")

    def test_malformed_uuid_in_path_is_json_404(self):
        self.as_user(self.owner)
        response = self.api.get("/api/projects/not-a-uuid/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["code"], "NOT_FOUND")

    def test_wrong_method_is_json_405(self):
        self.as_user(self.owner)
        response = self.api.delete(reverse("project-list-create"))
        self.assertError(response, 405, "METHOD_NOT_ALLOWED")

    def test_unexpected_error_does_not_leak_details(self):
        self.as_user(self.owner)
        with mock.patch(
            "projects.views.paginate",
            side_effect=RuntimeError("secret internal detail"),
        ):
            with self.assertLogs("projects.api", level="ERROR"):
                response = self.api.get(reverse("project-list-create"))
        self.assertError(response, 500, "INTERNAL_SERVER_ERROR")
        self.assertNotIn("secret", str(response.data))

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_disallowed_host_is_json_400(self):
        response = APIClient().get(
            reverse("health"), HTTP_HOST="evil.example.com"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["code"], "VALIDATION_ERROR")

    def test_health_uses_success_envelope_and_is_public(self):
        response = APIClient().get(reverse("health"))
        self.assertSuccess(response)
        self.assertEqual(
            response.data["data"],
            {"service": "project-service", "status": "healthy"},
        )

    def test_health_ignores_a_bad_token(self):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        self.assertEqual(api.get(reverse("health")).status_code, 200)


# ============================================================ pagination tests

class PaginationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        for index in range(3):
            project_id = self.create_project(title=f"Project {index}")
            self.publish(project_id)
        self.as_user(self.student)
        self.url = reverse("project-list-create")

    def test_page_size_limits_results(self):
        response = self.api.get(self.url, {"page_size": 2})
        self.assertEqual(len(response.data["data"]), 2)
        self.assertEqual(
            response.data["pagination"],
            {"page": 1, "page_size": 2, "total": 3, "total_pages": 2},
        )

    def test_second_page_has_the_remainder(self):
        response = self.api.get(self.url, {"page": 2, "page_size": 2})
        self.assertEqual(len(response.data["data"]), 1)

    def test_page_past_the_end_is_empty(self):
        response = self.api.get(self.url, {"page": 9})
        self.assertEqual(response.data["data"], [])
        self.assertEqual(response.data["pagination"]["total"], 3)

    def test_zero_results_has_zero_total_pages(self):
        response = self.api.get(self.url, {"category": "nothing"})
        self.assertEqual(response.data["data"], [])
        self.assertEqual(
            response.data["pagination"],
            {"page": 1, "page_size": 20, "total": 0, "total_pages": 0},
        )

    def test_page_size_above_maximum_is_rejected(self):
        response = self.api.get(self.url, {"page_size": 101})
        self.assertError(response, 400, "VALIDATION_ERROR")
        self.assertIn("page_size", response.data["details"]["fields"])

    def test_maximum_page_size_is_accepted(self):
        response = self.api.get(self.url, {"page_size": 100})
        self.assertEqual(response.status_code, 200)

    def test_invalid_page_values_are_rejected(self):
        for params in ({"page": 0}, {"page": "abc"}, {"page_size": -1}):
            response = self.api.get(self.url, params)
            self.assertError(response, 400, "VALIDATION_ERROR")


# ====================================================== permission tests

class ProjectPermissionTests(ApiTestCase):
    def test_student_cannot_create_project(self):
        self.as_user(self.student)
        response = self.api.post(
            reverse("project-list-create"), project_payload()
        )
        self.assertError(response, 403, "FORBIDDEN")

    def test_admin_cannot_create_project(self):
        self.as_user(self.admin)
        response = self.api.post(
            reverse("project-list-create"), project_payload()
        )
        self.assertError(response, 403, "FORBIDDEN")

    def test_other_users_cannot_see_a_draft(self):
        project_id = self.create_project()
        for user in (self.student, self.other_client):
            self.as_user(user)
            response = self.api.get(self.detail_url(project_id))
            self.assertError(response, 404, "NOT_FOUND")

    def test_owner_and_admin_can_see_a_draft(self):
        project_id = self.create_project()
        for user in (self.owner, self.admin):
            self.as_user(user)
            response = self.api.get(self.detail_url(project_id))
            self.assertSuccess(response)

    def test_students_can_view_a_published_project(self):
        project_id = self.create_project()
        self.publish(project_id)
        self.as_user(self.student)
        response = self.api.get(self.detail_url(project_id))
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["status"], "PUBLISHED")

    def test_students_can_view_a_non_draft_project_by_id(self):
        project_id = self.create_project()
        Project.objects.filter(pk=project_id).update(
            status=Project.Status.IN_PROGRESS
        )
        self.as_user(self.student)
        self.assertSuccess(self.api.get(self.detail_url(project_id)))

    def test_student_list_shows_only_published(self):
        draft_id = self.create_project()
        published_id = self.create_project()
        self.publish(published_id)

        self.as_user(self.student)
        response = self.api.get(reverse("project-list-create"))
        ids = [item["id"] for item in response.data["data"]]
        self.assertIn(published_id, ids)
        self.assertNotIn(draft_id, ids)

    def test_client_list_includes_own_drafts_only(self):
        own_draft = self.create_project(owner=self.owner)
        other_draft = self.create_project(owner=self.other_client)

        self.as_user(self.owner)
        response = self.api.get(reverse("project-list-create"))
        ids = [item["id"] for item in response.data["data"]]
        self.assertIn(own_draft, ids)
        self.assertNotIn(other_draft, ids)

    def test_client_sees_own_draft_even_when_filtering(self):
        project_id = self.create_project()
        self.as_user(self.owner)
        response = self.api.get(
            reverse("project-list-create"), {"skill": "python"}
        )
        ids = [item["id"] for item in response.data["data"]]
        self.assertIn(project_id, ids)

    def test_admin_list_includes_every_project(self):
        draft_id = self.create_project()
        self.as_user(self.admin)
        response = self.api.get(reverse("project-list-create"))
        ids = [item["id"] for item in response.data["data"]]
        self.assertIn(draft_id, ids)

    def test_list_filters_by_query_params(self):
        project_id = self.create_project()
        self.publish(project_id)

        self.as_user(self.student)
        url = reverse("project-list-create")

        response = self.api.get(
            url,
            {
                "query": "django",
                "skill": "python",
                "category": "software",
                "max_budget": "20000",
            },
        )
        self.assertEqual(len(response.data["data"]), 1)

        response = self.api.get(url, {"max_budget": "100"})
        self.assertEqual(len(response.data["data"]), 0)

        response = self.api.get(url, {"max_budget": "abc"})
        self.assertError(response, 400, "VALIDATION_ERROR")
        self.assertIn("max_budget", response.data["details"]["fields"])

    def test_other_client_cannot_edit_a_published_project(self):
        project_id = self.create_project()
        self.publish(project_id)
        self.as_user(self.other_client)
        response = self.api.put(
            self.detail_url(project_id), {"title": "Hijacked"}
        )
        self.assertError(response, 403, "FORBIDDEN")

    def test_student_cannot_edit_project(self):
        project_id = self.create_project()
        self.publish(project_id)
        self.as_user(self.student)
        response = self.api.patch(
            self.detail_url(project_id), {"title": "Hijacked"}
        )
        self.assertError(response, 403, "FORBIDDEN")

    def test_owner_can_edit_with_put_and_patch(self):
        project_id = self.create_project()
        self.as_user(self.owner)

        response = self.api.put(
            self.detail_url(project_id), {"title": "New title"}
        )
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["title"], "New title")

        response = self.api.patch(
            self.detail_url(project_id), {"category": "Web"}
        )
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["category"], "Web")

    def test_owner_can_close_and_status_changes(self):
        project_id = self.create_project()
        self.as_user(self.owner)
        response = self.api.post(
            reverse("project-close", kwargs={"project_id": project_id})
        )
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["status"], "CLOSED")

    def test_other_client_cannot_close_or_delete_a_published_project(self):
        project_id = self.create_project()
        self.publish(project_id)
        self.as_user(self.other_client)

        response = self.api.post(
            reverse("project-close", kwargs={"project_id": project_id})
        )
        self.assertError(response, 403, "FORBIDDEN")

        response = self.api.delete(self.detail_url(project_id))
        self.assertError(response, 403, "FORBIDDEN")

    def test_student_cannot_publish_or_close(self):
        project_id = self.create_project()
        self.publish(project_id)
        self.as_user(self.student)
        for name in ("project-publish", "project-close"):
            response = self.api.post(
                reverse(name, kwargs={"project_id": project_id})
            )
            self.assertError(response, 403, "FORBIDDEN")

    def test_admin_can_close_any_project(self):
        project_id = self.create_project()
        self.publish(project_id)
        self.as_user(self.admin)
        response = self.api.post(
            reverse("project-close", kwargs={"project_id": project_id})
        )
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["status"], "CLOSED")

    def test_admin_cannot_publish_a_clients_project(self):
        project_id = self.create_project()
        self.as_user(self.admin)
        response = self.api.post(
            reverse("project-publish", kwargs={"project_id": project_id})
        )
        self.assertError(response, 403, "FORBIDDEN")

    def test_status_endpoint_is_owner_or_admin_only(self):
        project_id = self.create_project()
        self.publish(project_id)
        url = reverse("project-status", kwargs={"project_id": project_id})

        for user in (self.owner, self.admin):
            self.as_user(user)
            response = self.api.get(url)
            self.assertSuccess(response)
            self.assertEqual(response.data["data"]["status"], "PUBLISHED")

        self.as_user(self.student)
        self.assertError(self.api.get(url), 403, "FORBIDDEN")

        self.as_user(self.other_client)
        self.assertError(self.api.get(url), 403, "FORBIDDEN")

    def test_status_of_someone_elses_draft_is_hidden(self):
        project_id = self.create_project()
        self.as_user(self.student)
        response = self.api.get(
            reverse("project-status", kwargs={"project_id": project_id})
        )
        self.assertError(response, 404, "NOT_FOUND")


# ====================================================== lifecycle tests

class ProjectLifecycleApiTests(ApiTestCase):
    def test_publish_moves_draft_to_published(self):
        project_id = self.create_project()
        response = self.publish(project_id)
        self.assertEqual(response.data["data"]["status"], "PUBLISHED")

    def test_publishing_twice_is_an_invalid_transition(self):
        project_id = self.create_project()
        self.publish(project_id)
        response = self.api.post(
            reverse("project-publish", kwargs={"project_id": project_id})
        )
        self.assertError(response, 400, "INVALID_STATE_TRANSITION")

    def test_closing_twice_is_an_invalid_transition(self):
        project_id = self.create_project()
        url = reverse("project-close", kwargs={"project_id": project_id})
        self.assertSuccess(self.api.post(url))
        self.assertError(self.api.post(url), 400, "INVALID_STATE_TRANSITION")

    def test_closed_project_cannot_be_edited(self):
        project_id = self.create_project()
        self.api.post(
            reverse("project-close", kwargs={"project_id": project_id})
        )
        response = self.api.put(
            self.detail_url(project_id), {"title": "Too late"}
        )
        self.assertError(response, 400, "INVALID_STATE_TRANSITION")

    def test_in_progress_project_cannot_be_edited(self):
        project_id = self.create_project()
        Project.objects.filter(pk=project_id).update(
            status=Project.Status.IN_PROGRESS
        )
        response = self.api.patch(
            self.detail_url(project_id), {"budget": "99999.00"}
        )
        self.assertError(response, 400, "INVALID_STATE_TRANSITION")

    def test_past_deadline_cannot_be_published(self):
        project_id = self.create_project()
        Project.objects.filter(pk=project_id).update(
            deadline=date.today() - timedelta(days=2)
        )
        response = self.api.post(
            reverse("project-publish", kwargs={"project_id": project_id})
        )
        self.assertError(response, 400, "VALIDATION_ERROR")

    def test_draft_can_be_deleted_with_json_envelope(self):
        project_id = self.create_project()
        response = self.api.delete(self.detail_url(project_id))
        self.assertSuccess(response)
        self.assertEqual(response.data["data"], {"id": project_id})
        self.assertFalse(Project.objects.filter(pk=project_id).exists())

    def test_admin_can_delete_a_draft(self):
        project_id = self.create_project()
        self.as_user(self.admin)
        self.assertSuccess(self.api.delete(self.detail_url(project_id)))

    def test_published_project_cannot_be_deleted(self):
        project_id = self.create_project()
        self.publish(project_id)
        response = self.api.delete(self.detail_url(project_id))
        self.assertError(response, 400, "INVALID_STATE_TRANSITION")

    def action_url(self, name, project_id):
        return reverse(f"project-{name}", kwargs={"project_id": project_id})

    def test_start_and_complete_are_idempotent(self):
        project_id = self.create_project()
        self.publish(project_id)

        for _ in range(2):
            response = self.api.post(self.action_url("start", project_id))
            self.assertSuccess(response)
            self.assertEqual(response.data["data"]["status"], "IN_PROGRESS")

        for _ in range(2):
            response = self.api.post(self.action_url("complete", project_id))
            self.assertSuccess(response)
            self.assertEqual(response.data["data"]["status"], "COMPLETED")

    def test_draft_cannot_be_started(self):
        project_id = self.create_project()
        response = self.api.post(self.action_url("start", project_id))
        self.assertError(response, 400, "INVALID_STATE_TRANSITION")

    def test_published_project_cannot_be_completed(self):
        project_id = self.create_project()
        self.publish(project_id)
        response = self.api.post(self.action_url("complete", project_id))
        self.assertError(response, 400, "INVALID_STATE_TRANSITION")

    def test_only_owner_can_start(self):
        project_id = self.create_project()
        self.publish(project_id)
        self.as_user(self.other_client)
        response = self.api.post(self.action_url("start", project_id))
        self.assertError(response, 403, "FORBIDDEN")
        self.as_user(self.student)
        response = self.api.post(self.action_url("start", project_id))
        self.assertError(response, 403, "FORBIDDEN")


# ======================================== real JWT authentication tests

class JWTAuthenticationTests(TestCase):
    """These use real signed tokens, not force_authenticate."""

    def setUp(self):
        self.url = reverse("project-list-create")

    def request(self, token=None, header=None):
        api = APIClient()
        if header is not None:
            api.credentials(HTTP_AUTHORIZATION=header)
        elif token is not None:
            api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return api.get(self.url)

    def assertUnauthorized(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "UNAUTHORIZED")
        self.assertTrue(response.data["error"])
        self.assertEqual(response.data["details"], {})
        self.assertEqual(response["WWW-Authenticate"], "Bearer")

    def test_missing_token_is_rejected(self):
        self.assertUnauthorized(self.request())

    def test_wrong_scheme_is_rejected(self):
        self.assertUnauthorized(self.request(header="Basic abc123"))

    def test_extra_header_parts_are_rejected(self):
        self.assertUnauthorized(self.request(header="Bearer a b"))

    def test_malformed_token_is_rejected(self):
        self.assertUnauthorized(self.request("not-a-real-token"))

    def test_expired_token_is_rejected(self):
        self.assertUnauthorized(self.request(make_token(exp_delta=-3600)))

    def test_wrong_signature_is_rejected(self):
        token = make_token(secret="some-other-secret-key-of-32-chars!!")
        self.assertUnauthorized(self.request(token))

    def test_other_algorithm_is_rejected(self):
        self.assertUnauthorized(self.request(make_token(algorithm="HS384")))

    def test_refresh_token_is_rejected(self):
        self.assertUnauthorized(
            self.request(make_token(token_type="refresh"))
        )

    def test_missing_claims_are_rejected(self):
        for claim in ("user_id", "role", "token_type", "exp", "iat"):
            with self.subTest(claim=claim):
                self.assertUnauthorized(
                    self.request(make_token(drop=(claim,)))
                )

    def test_invalid_role_is_rejected(self):
        for role in ("SUPERUSER", "client", "", None, 7):
            with self.subTest(role=role):
                self.assertUnauthorized(self.request(make_token(role=role)))

    def test_non_uuid_user_id_is_rejected(self):
        # Integer IDs (the User service today) must not be accepted.
        for value in ("42", 42, "not-a-uuid", uuid.uuid4().hex):
            with self.subTest(user_id=value):
                self.assertUnauthorized(
                    self.request(make_token(user_id=value))
                )

    def test_valid_token_for_each_role_is_accepted(self):
        for role in ("STUDENT", "CLIENT", "ADMIN"):
            with self.subTest(role=role):
                response = self.request(make_token(role=role))
                self.assertEqual(response.status_code, 200)

    def test_client_token_creates_project_owned_by_token_user(self):
        user_id = uuid.uuid4()
        api = APIClient()
        api.credentials(
            HTTP_AUTHORIZATION=f"Bearer {make_token('CLIENT', user_id)}"
        )
        response = api.post(self.url, project_payload())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["data"]["client_id"], str(user_id))

    def test_student_token_cannot_create_project(self):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token('STUDENT')}")
        response = api.post(self.url, project_payload())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "FORBIDDEN")

    def test_ownership_comes_from_the_token_not_the_body(self):
        owner_id, other_id = uuid.uuid4(), uuid.uuid4()
        owner = APIClient()
        owner.credentials(
            HTTP_AUTHORIZATION=f"Bearer {make_token('CLIENT', owner_id)}"
        )
        project_id = owner.post(self.url, project_payload()).data["data"]["id"]

        other = APIClient()
        other.credentials(
            HTTP_AUTHORIZATION=f"Bearer {make_token('CLIENT', other_id)}"
        )
        response = other.post(
            reverse("project-publish", kwargs={"project_id": project_id})
        )
        self.assertEqual(response.status_code, 404)  # a draft stays hidden