import time
import uuid
from unittest.mock import patch

import jwt
from django.conf import settings
from rest_framework.test import APITestCase

from .api import ApiError
from .models import Application, ApplicationStatus, Assignment, AssignmentStatus

STUDENT = uuid.uuid4()
OTHER_STUDENT = uuid.uuid4()
CLIENT = uuid.uuid4()
OTHER_CLIENT = uuid.uuid4()
ADMIN = uuid.uuid4()
PROJECT = uuid.uuid4()


def make_token(user_id, role, token_type="access", exp_offset=1800, **overrides):
    now = int(time.time())
    payload = {
        "user_id": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + exp_offset,
        "token_type": token_type,
    }
    payload.update(overrides)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def project_data(status="PUBLISHED", client_id=CLIENT, project_id=PROJECT):
    return {
        "id": str(project_id),
        "client_id": str(client_id),
        "status": status,
        "budget": "500.00",
    }


class BaseTestCase(APITestCase):
    def setUp(self):
        get_patcher = patch("applications.views.get_project")
        start_patcher = patch("applications.views.start_project")
        self.get_project = get_patcher.start()
        self.start_project = start_patcher.start()
        self.addCleanup(get_patcher.stop)
        self.addCleanup(start_patcher.stop)
        self.get_project.return_value = project_data()
        self.start_project.return_value = project_data("IN_PROGRESS")

    def as_user(self, user_id, role):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_token(user_id, role)}")

    def make_application(self, student=STUDENT, status=ApplicationStatus.SUBMITTED, project=PROJECT):
        return Application.objects.create(
            student_id=student, project_id=project, proposal="I can do it", status=status
        )

    def assertError(self, response, http_status, code):
        self.assertEqual(response.status_code, http_status, response.content)
        body = response.json()
        self.assertEqual(body["code"], code)
        self.assertIsInstance(body["error"], str)
        self.assertIn("details", body)


class AuthenticationTests(BaseTestCase):
    def test_health_is_public_and_enveloped(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "healthy")

    def test_missing_token_returns_401(self):
        self.assertError(self.client.get("/api/applications/"), 401, "UNAUTHORIZED")

    def test_expired_token_returns_401(self):
        token = make_token(STUDENT, "STUDENT", exp_offset=-10)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertError(self.client.get("/api/applications/"), 401, "UNAUTHORIZED")

    def test_refresh_token_is_rejected(self):
        token = make_token(STUDENT, "STUDENT", token_type="refresh")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertError(self.client.get("/api/applications/"), 401, "UNAUTHORIZED")

    def test_invalid_role_is_rejected(self):
        token = make_token(STUDENT, "SUPERUSER")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertError(self.client.get("/api/applications/"), 401, "UNAUTHORIZED")

    def test_non_uuid_user_id_is_rejected(self):
        token = make_token("42", "STUDENT")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertError(self.client.get("/api/applications/"), 401, "UNAUTHORIZED")

    def test_wrong_signature_is_rejected(self):
        now = int(time.time())
        token = jwt.encode(
            {"user_id": str(STUDENT), "role": "STUDENT", "iat": now, "exp": now + 60, "token_type": "access"},
            "another-secret-another-secret-another",
            algorithm="HS256",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertError(self.client.get("/api/applications/"), 401, "UNAUTHORIZED")

    def test_unknown_route_returns_json_404(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.get("/api/does-not-exist/")
        self.assertError(response, 404, "NOT_FOUND")


class ApplyTests(BaseTestCase):
    def test_student_applies_with_identity_from_token(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.post(
            "/api/applications/", {"project_id": str(PROJECT), "proposal": "Hire me"}
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["data"]["student_id"], str(STUDENT))
        self.assertEqual(body["data"]["status"], "submitted")
        self.assertTrue(body["message"])

    def test_body_identity_fields_are_rejected(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.post(
            "/api/applications/",
            {"project_id": str(PROJECT), "proposal": "Hire me", "student_id": str(OTHER_STUDENT)},
        )
        self.assertError(response, 400, "VALIDATION_ERROR")
        self.assertIn("student_id", response.json()["details"]["fields"])

    def test_client_cannot_apply(self):
        self.as_user(CLIENT, "CLIENT")
        response = self.client.post(
            "/api/applications/", {"project_id": str(PROJECT), "proposal": "x"}
        )
        self.assertError(response, 403, "FORBIDDEN")

    def test_validation_errors_use_fields(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.post("/api/applications/", {"proposal": ""})
        self.assertError(response, 400, "VALIDATION_ERROR")
        self.assertIn("project_id", response.json()["details"]["fields"])

    def test_unpublished_project_is_rejected(self):
        self.get_project.return_value = project_data("DRAFT")
        self.as_user(STUDENT, "STUDENT")
        response = self.client.post(
            "/api/applications/", {"project_id": str(PROJECT), "proposal": "Hire me"}
        )
        self.assertError(response, 400, "INVALID_STATE_TRANSITION")

    def test_missing_project_returns_404(self):
        self.get_project.side_effect = ApiError("Project not found.", "NOT_FOUND", 404)
        self.as_user(STUDENT, "STUDENT")
        response = self.client.post(
            "/api/applications/", {"project_id": str(PROJECT), "proposal": "Hire me"}
        )
        self.assertError(response, 404, "NOT_FOUND")

    def test_project_service_down_returns_503(self):
        self.get_project.side_effect = ApiError("down", "UPSTREAM_SERVICE_ERROR", 503)
        self.as_user(STUDENT, "STUDENT")
        response = self.client.post(
            "/api/applications/", {"project_id": str(PROJECT), "proposal": "Hire me"}
        )
        self.assertError(response, 503, "UPSTREAM_SERVICE_ERROR")

    def test_duplicate_application_returns_409(self):
        self.make_application()
        self.as_user(STUDENT, "STUDENT")
        response = self.client.post(
            "/api/applications/", {"project_id": str(PROJECT), "proposal": "Again"}
        )
        self.assertError(response, 409, "DUPLICATE_APPLICATION")


class ListAndDetailTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.mine = self.make_application()
        self.theirs = self.make_application(student=OTHER_STUDENT)

    def test_student_lists_only_own_applications(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.get("/api/applications/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([a["id"] for a in body["data"]], [str(self.mine.id)])
        self.assertEqual(
            body["pagination"], {"page": 1, "page_size": 20, "total": 1, "total_pages": 1}
        )

    def test_student_cannot_list_another_students_applications(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.get(f"/api/applications/?student_id={OTHER_STUDENT}")
        self.assertError(response, 403, "FORBIDDEN")

    def test_owning_client_lists_project_applications(self):
        self.as_user(CLIENT, "CLIENT")
        response = self.client.get(f"/api/applications/?project_id={PROJECT}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pagination"]["total"], 2)

    def test_client_must_supply_project_id(self):
        self.as_user(CLIENT, "CLIENT")
        self.assertError(self.client.get("/api/applications/"), 400, "VALIDATION_ERROR")

    def test_non_owning_client_cannot_list(self):
        self.as_user(OTHER_CLIENT, "CLIENT")
        response = self.client.get(f"/api/applications/?project_id={PROJECT}")
        self.assertError(response, 403, "FORBIDDEN")

    def test_invalid_uuid_filter_returns_400(self):
        self.as_user(CLIENT, "CLIENT")
        response = self.client.get("/api/applications/?project_id=abc")
        self.assertError(response, 400, "VALIDATION_ERROR")

    def test_pagination_validation(self):
        self.as_user(STUDENT, "STUDENT")
        self.assertError(self.client.get("/api/applications/?page=0"), 400, "VALIDATION_ERROR")
        self.assertError(self.client.get("/api/applications/?page_size=101"), 400, "VALIDATION_ERROR")

    def test_empty_collection_has_zero_total_pages(self):
        self.as_user(uuid.uuid4(), "STUDENT")
        body = self.client.get("/api/applications/").json()
        self.assertEqual(body["data"], [])
        self.assertEqual(body["pagination"]["total_pages"], 0)

    def test_applicant_reads_own_application(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.get(f"/api/applications/{self.mine.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["id"], str(self.mine.id))

    def test_other_student_cannot_read_application(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.get(f"/api/applications/{self.theirs.id}/")
        self.assertError(response, 403, "FORBIDDEN")

    def test_owning_client_reads_application(self):
        self.as_user(CLIENT, "CLIENT")
        self.assertEqual(self.client.get(f"/api/applications/{self.mine.id}/").status_code, 200)

    def test_admin_reads_application_without_project_lookup(self):
        self.as_user(ADMIN, "ADMIN")
        self.assertEqual(self.client.get(f"/api/applications/{self.mine.id}/").status_code, 200)
        self.get_project.assert_not_called()

    def test_missing_application_returns_404(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.get(f"/api/applications/{uuid.uuid4()}/")
        self.assertError(response, 404, "NOT_FOUND")

    def test_applicant_updates_submitted_application(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.patch(
            f"/api/applications/{self.mine.id}/", {"proposal": "Better proposal"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["proposal"], "Better proposal")

    def test_update_rejects_status_field(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.patch(
            f"/api/applications/{self.mine.id}/", {"status": "selected"}
        )
        self.assertError(response, 400, "VALIDATION_ERROR")

    def test_cannot_update_after_shortlisting(self):
        self.mine.status = ApplicationStatus.SHORTLISTED
        self.mine.save()
        self.as_user(STUDENT, "STUDENT")
        response = self.client.patch(f"/api/applications/{self.mine.id}/", {"proposal": "x"})
        self.assertError(response, 400, "INVALID_STATE_TRANSITION")

    def test_other_student_cannot_update(self):
        self.as_user(OTHER_STUDENT, "STUDENT")
        response = self.client.patch(f"/api/applications/{self.mine.id}/", {"proposal": "x"})
        self.assertError(response, 403, "FORBIDDEN")


class TransitionTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.application = self.make_application()

    def post(self, action, user=CLIENT, role="CLIENT", application=None):
        self.as_user(user, role)
        app = application or self.application
        return self.client.post(f"/api/applications/{app.id}/{action}/")

    def test_owner_shortlists(self):
        response = self.post("shortlist")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "shortlisted")

    def test_non_owner_cannot_shortlist(self):
        self.assertError(self.post("shortlist", user=OTHER_CLIENT), 403, "FORBIDDEN")

    def test_student_cannot_shortlist(self):
        self.assertError(self.post("shortlist", user=STUDENT, role="STUDENT"), 403, "FORBIDDEN")

    def test_select_requires_shortlist(self):
        self.assertError(self.post("select"), 400, "INVALID_STATE_TRANSITION")
        self.assertFalse(Assignment.objects.exists())

    def test_select_creates_assignment_and_starts_project(self):
        other = self.make_application(student=OTHER_STUDENT)
        self.post("shortlist")
        response = self.post("select")
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()["data"]
        self.assertEqual(data["application"]["status"], "selected")
        assignment = data["assignment"]
        self.assertEqual(assignment["student_id"], str(STUDENT))
        self.assertEqual(assignment["client_id"], str(CLIENT))
        self.assertEqual(assignment["project_id"], str(PROJECT))
        self.assertEqual(assignment["status"], "active")
        self.start_project.assert_called_once()
        other.refresh_from_db()
        self.assertEqual(other.status, ApplicationStatus.REJECTED)

    def test_select_rolls_back_when_project_start_fails(self):
        self.post("shortlist")
        self.start_project.side_effect = ApiError("down", "UPSTREAM_SERVICE_ERROR", 503)
        self.assertError(self.post("select"), 503, "UPSTREAM_SERVICE_ERROR")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.SHORTLISTED)
        self.assertFalse(Assignment.objects.exists())

    def test_second_selection_for_project_conflicts(self):
        self.post("shortlist")
        self.post("select")
        second = self.make_application(student=OTHER_STUDENT, status=ApplicationStatus.SHORTLISTED)
        self.assertError(self.post("select", application=second), 409, "CONFLICT")

    def test_select_on_closed_project_is_rejected(self):
        self.post("shortlist")
        self.get_project.return_value = project_data("CLOSED")
        self.assertError(self.post("select"), 400, "INVALID_STATE_TRANSITION")

    def test_reject(self):
        response = self.post("reject")
        self.assertEqual(response.json()["data"]["status"], "rejected")
        self.assertError(self.post("shortlist"), 400, "INVALID_STATE_TRANSITION")

    def test_applicant_withdraws(self):
        response = self.post("withdraw", user=STUDENT, role="STUDENT")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "withdrawn")
        self.assertError(
            self.post("withdraw", user=STUDENT, role="STUDENT"), 400, "INVALID_STATE_TRANSITION"
        )

    def test_other_student_cannot_withdraw(self):
        self.assertError(self.post("withdraw", user=OTHER_STUDENT, role="STUDENT"), 403, "FORBIDDEN")


class AssignmentTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        application = self.make_application(status=ApplicationStatus.SELECTED)
        self.assignment = Assignment.objects.create(
            application_id=application.id,
            student_id=STUDENT,
            client_id=CLIENT,
            project_id=PROJECT,
        )
        other_app = self.make_application(student=OTHER_STUDENT, project=uuid.uuid4())
        self.other = Assignment.objects.create(
            application_id=other_app.id,
            student_id=OTHER_STUDENT,
            client_id=OTHER_CLIENT,
            project_id=other_app.project_id,
        )

    def test_participants_list_only_their_assignments(self):
        for user, role in ((STUDENT, "STUDENT"), (CLIENT, "CLIENT")):
            self.as_user(user, role)
            body = self.client.get("/api/assignments/").json()
            self.assertEqual([a["id"] for a in body["data"]], [str(self.assignment.id)])
            self.assertEqual(body["pagination"]["total"], 1)

    def test_admin_lists_all_and_filters_by_project(self):
        self.as_user(ADMIN, "ADMIN")
        self.assertEqual(self.client.get("/api/assignments/").json()["pagination"]["total"], 2)
        body = self.client.get(f"/api/assignments/?project_id={PROJECT}").json()
        self.assertEqual(len(body["data"]), 1)

    def test_participant_reads_assignment(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.get(f"/api/assignments/{self.assignment.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["client_id"], str(CLIENT))

    def test_non_participant_gets_404(self):
        self.as_user(OTHER_STUDENT, "STUDENT")
        response = self.client.get(f"/api/assignments/{self.assignment.id}/")
        self.assertError(response, 404, "NOT_FOUND")

    def test_owning_client_completes_assignment_idempotently(self):
        self.as_user(CLIENT, "CLIENT")
        url = f"/api/assignments/{self.assignment.id}/complete/"
        first = self.client.post(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["status"], AssignmentStatus.COMPLETED)
        self.assertIsNotNone(first.json()["data"]["completion_date"])
        second = self.client.post(url)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["data"]["completion_date"], first.json()["data"]["completion_date"])

    def test_student_cannot_complete_assignment(self):
        self.as_user(STUDENT, "STUDENT")
        response = self.client.post(f"/api/assignments/{self.assignment.id}/complete/")
        self.assertError(response, 403, "FORBIDDEN")

    def test_other_client_cannot_complete_assignment(self):
        self.as_user(OTHER_CLIENT, "CLIENT")
        response = self.client.post(f"/api/assignments/{self.assignment.id}/complete/")
        self.assertError(response, 404, "NOT_FOUND")
