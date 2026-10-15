from datetime import date, timedelta
from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from rest_framework.test import APIClient

from .models import Project
from .services import (
    NotProjectOwner,
    close_project,
    create_project,
    publish_project,
    search_projects,
    update_project,
)


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
        with self.assertRaises(ValidationError):
            update_project(
                project=self.project,
                client_id=self.client_id,
                title="Too late",
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


class FakeUser:
    """Minimal stand-in for the user object from the auth layer."""

    is_authenticated = True
    is_staff = False
    is_superuser = False

    def __init__(self, role, user_id=None):
        self.role = role
        self.id = user_id or uuid.uuid4()


@override_settings(ROOT_URLCONF="projects.urls")
class ProjectAPITests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.owner = FakeUser("client")
        self.other_client = FakeUser("client")
        self.student = FakeUser("student")

        self.payload = {
            "title": "Build a Django API",
            "description": "Develop a REST API for a student project.",
            "skills": ["Python", "Django"],
            "category": "Software",
            "budget": "15000.00",
            "deadline": (date.today() + timedelta(days=30)).isoformat(),
        }

    def _create_project(self):
        self.api.force_authenticate(user=self.owner)
        response = self.api.post(
            reverse("project-list-create"), self.payload, format="json"
        )
        self.assertEqual(response.status_code, 201)
        return response.data["data"]["id"]

    def _publish(self, project_id):
        self.api.force_authenticate(user=self.owner)
        response = self.api.post(
            reverse("project-publish", kwargs={"project_id": project_id})
        )
        self.assertEqual(response.status_code, 200)

    def test_client_creates_draft_project(self):
        self.api.force_authenticate(user=self.owner)
        response = self.api.post(
            reverse("project-list-create"), self.payload, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["status"], "DRAFT")
        self.assertEqual(
            response.data["data"]["client_id"], str(self.owner.id)
        )

    def test_student_cannot_create_project(self):
        self.api.force_authenticate(user=self.student)
        response = self.api.post(
            reverse("project-list-create"), self.payload, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_view_draft(self):
        project_id = self._create_project()
        self.api.force_authenticate(user=self.student)
        response = self.api.get(
            reverse("project-detail", kwargs={"project_id": project_id})
        )
        self.assertEqual(response.status_code, 403)

    def test_student_can_view_published_project_in_data_envelope(self):
        project_id = self._create_project()
        self._publish(project_id)

        self.api.force_authenticate(user=self.student)
        response = self.api.get(
            reverse("project-detail", kwargs={"project_id": project_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["id"], project_id)
        self.assertEqual(response.data["data"]["status"], "PUBLISHED")

    def test_student_list_shows_only_published(self):
        draft_id = self._create_project()
        published_id = self._create_project()
        self._publish(published_id)

        self.api.force_authenticate(user=self.student)
        response = self.api.get(reverse("project-list-create"))
        ids = [item["id"] for item in response.data["data"]]
        self.assertIn(published_id, ids)
        self.assertNotIn(draft_id, ids)

    def test_client_sees_own_draft_even_when_filtering(self):
        project_id = self._create_project()
        response = self.api.get(
            reverse("project-list-create"), {"skill": "python"}
        )
        ids = [item["id"] for item in response.data["data"]]
        self.assertIn(project_id, ids)

    def test_list_filters_by_query_params(self):
        project_id = self._create_project()
        self._publish(project_id)

        self.api.force_authenticate(user=self.student)
        url = reverse("project-list-create")

        response = self.api.get(
            url,
            {"skill": "python", "category": "software", "max_budget": "20000"},
        )
        self.assertEqual(len(response.data["data"]), 1)

        response = self.api.get(url, {"max_budget": "100"})
        self.assertEqual(len(response.data["data"]), 0)

        response = self.api.get(url, {"max_budget": "abc"})
        self.assertEqual(response.status_code, 400)

    def test_other_client_cannot_edit_project(self):
        project_id = self._create_project()
        self.api.force_authenticate(user=self.other_client)
        response = self.api.put(
            reverse("project-detail", kwargs={"project_id": project_id}),
            {"title": "Hijacked"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_edit_and_close_project(self):
        project_id = self._create_project()
        self.api.force_authenticate(user=self.owner)

        response = self.api.put(
            reverse("project-detail", kwargs={"project_id": project_id}),
            {"title": "New title"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["title"], "New title")

        response = self.api.post(
            reverse("project-close", kwargs={"project_id": project_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], "CLOSED")

    def test_other_client_cannot_close_or_delete_project(self):
        project_id = self._create_project()
        self.api.force_authenticate(user=self.other_client)

        response = self.api.post(
            reverse("project-close", kwargs={"project_id": project_id})
        )
        self.assertEqual(response.status_code, 403)

        response = self.api.delete(
            reverse("project-detail", kwargs={"project_id": project_id})
        )
        self.assertEqual(response.status_code, 403)

    def test_status_endpoint_is_owner_only(self):
        project_id = self._create_project()
        url = reverse("project-status", kwargs={"project_id": project_id})

        self.api.force_authenticate(user=self.owner)
        self.assertEqual(self.api.get(url).status_code, 200)

        self.api.force_authenticate(user=self.student)
        self.assertEqual(self.api.get(url).status_code, 403)
