
from datetime import date, timedelta
from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Project
from .services import (
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
        publish_project(
            project=self.project,
            client_id=self.client_id,
        )
        self.project.refresh_from_db()

        self.assertEqual(
            self.project.status,
            Project.Status.PUBLISHED,
        )

    def test_only_owner_can_publish_project(self):
        with self.assertRaises(ValidationError):
            publish_project(
                project=self.project,
                client_id=self.other_client_id,
            )

    def test_published_project_can_be_closed(self):
        publish_project(
            project=self.project,
            client_id=self.client_id,
        )
        close_project(
            project=self.project,
            client_id=self.client_id,
        )
        self.project.refresh_from_db()

        self.assertEqual(
            self.project.status,
            Project.Status.CLOSED,
        )

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
        publish_project(
            project=self.project,
            client_id=self.client_id,
        )

        results = search_projects(query="Django")

        self.assertIn(self.project, results)

    def test_search_excludes_draft_projects(self):
        results = search_projects(query="Django")

        self.assertNotIn(self.project, results)

    def test_search_filters_by_skill(self):
        publish_project(
            project=self.project,
            client_id=self.client_id,
        )

        results = search_projects(skill="python")

        self.assertIn(self.project, results)

    def test_search_filters_by_maximum_budget(self):
        publish_project(
            project=self.project,
            client_id=self.client_id,
        )

        results = search_projects(max_budget="20000")

        self.assertIn(self.project, results)

        results = search_projects(max_budget="10000")

        self.assertNotIn(self.project, results)
