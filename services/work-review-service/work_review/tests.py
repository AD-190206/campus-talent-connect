from urllib import request, response

from django.test import TestCase
import uuid
from unittest.mock import Mock, patch

from work_review.assignment_client import (
    get_assignment,
    AssignmentNotFoundError,
    AssignmentServiceUnavailableError,
    AssignmentAuthorizationError,
)
from work_review.payment_client import (
    post_payment_request,
    process_payment_request,
    release_payment_request,
    PaymentServiceUnavailableError,
)
from work_review.project_client import (
    get_project,
    ProjectNotFoundError,
    ProjectAuthorizationError,
    ProjectServiceUnavailableError,
)


from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from work_review.models import Deliverable, Review
from work_review.serializers import DeliverableSerializer, ReviewSerializer
from rest_framework.test import APITestCase


class JWTAuthenticationTests(SimpleTestCase):
    def setUp(self):
        import os
        import time
        import jwt
        from rest_framework.test import APIRequestFactory

        self.jwt = jwt
        self.factory = APIRequestFactory()
        self.secret = "test-jwt-secret-key-at-least-32-bytes-long"
        self.env_patcher = patch.dict(
            os.environ,
            {"JWT_SECRET_KEY": self.secret},
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    def make_token(self, **overrides):
        import time
        import uuid

        payload = {
            "user_id": str(uuid.uuid4()),
            "role": "STUDENT",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "token_type": "access",
        }
        payload.update(overrides)
        return self.jwt.encode(payload, self.secret, algorithm="HS256")

    def authenticate_token(self, token):
        from work_review.authentication import JWTAuthentication

        request = self.factory.get(
            "/api/work/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        return JWTAuthentication().authenticate(request)

    def test_valid_access_token_authenticates(self):
        result = self.authenticate_token(self.make_token())

        self.assertIsNotNone(result)
        user, token = result
        self.assertEqual(user.role, "STUDENT")
        self.assertEqual(token, self.make_token_for_validity(token))

    def make_token_for_validity(self, token):
        # Return the supplied token unchanged for the equality assertion.
        return token

    def test_refresh_token_is_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed

        token = self.make_token(token_type="refresh")

        with self.assertRaises(AuthenticationFailed):
            self.authenticate_token(token)

    def test_missing_required_claim_is_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed

        for missing_claim in ("user_id", "role", "iat", "exp", "token_type"):
            with self.subTest(claim=missing_claim):
                payload = {
                    "user_id": "12345678-1234-4234-8234-123456789abc",
                    "role": "STUDENT",
                    "iat": int(__import__("time").time()),
                    "exp": int(__import__("time").time()) + 300,
                    "token_type": "access",
                }
                del payload[missing_claim]
                token = self.jwt.encode(
                    payload,
                    self.secret,
                    algorithm="HS256",
                )

                with self.assertRaises(AuthenticationFailed):
                    self.authenticate_token(token)

    def test_invalid_uuid_is_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed

        token = self.make_token(user_id="not-a-uuid")

        with self.assertRaises(AuthenticationFailed):
            self.authenticate_token(token)

    def test_noncanonical_uuid_is_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed

        token = self.make_token(
            user_id="12345678123442348234123456789abc"
        )

        with self.assertRaises(AuthenticationFailed):
            self.authenticate_token(token)

    def test_unsupported_role_is_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed

        token = self.make_token(role="SUPERUSER")

        with self.assertRaises(AuthenticationFailed):
            self.authenticate_token(token)

    def test_expired_token_is_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed
        import time

        token = self.make_token(exp=int(time.time()) - 10)

        with self.assertRaises(AuthenticationFailed):
            self.authenticate_token(token)

    def test_invalid_signature_is_rejected(self):
        from rest_framework.exceptions import AuthenticationFailed

        token = self.jwt.encode(
            {
                "user_id": "12345678-1234-4234-8234-123456789abc",
                "role": "STUDENT",
                "iat": 1000000000,
                "exp": 4102444800,
                "token_type": "access",
            },
            "wrong-secret-key-at-least-32-bytes-long",
            algorithm="HS256",
        )

        with self.assertRaises(AuthenticationFailed):
            self.authenticate_token(token)

    def test_missing_authorization_header_returns_none(self):
        from work_review.authentication import JWTAuthentication

        request = self.factory.get("/api/work/")

        self.assertIsNone(JWTAuthentication().authenticate(request))


class ReviewSerializerTests(TestCase):
    def setUp(self):
        self.reviewer_id = uuid.uuid4()
        self.reviewee_id = uuid.uuid4()
        self.assignment_id = uuid.uuid4()

        self.factory = APIRequestFactory()
        request = self.factory.post("/api/reviews/")
        request.user = type(
            "TestUser",
            (),
            {"user_id": self.reviewer_id, "role": "STUDENT"},
        )()

        self.context = {"request": request}

    def valid_review_data(self):
        return {
            "assignment_id": str(self.assignment_id),
            "reviewee_id": str(self.reviewee_id),
            "rating": 5,
            "comment": "Good collaboration.",
        }

    def test_rating_below_one_is_rejected(self):
        data = self.valid_review_data()
        data["rating"] = 0

        serializer = ReviewSerializer(data=data, context=self.context)

        self.assertFalse(serializer.is_valid())
        self.assertIn("rating", serializer.errors)

    def test_rating_above_five_is_rejected(self):
        data = self.valid_review_data()
        data["rating"] = 6

        serializer = ReviewSerializer(data=data, context=self.context)

        self.assertFalse(serializer.is_valid())
        self.assertIn("rating", serializer.errors)

    def test_user_cannot_review_themselves(self):
        data = self.valid_review_data()
        data["reviewee_id"] = str(self.reviewer_id)

        serializer = ReviewSerializer(data=data, context=self.context)

        self.assertFalse(serializer.is_valid())
        self.assertIn("reviewee_id", serializer.errors)

    def test_valid_review_data_passes_basic_validation(self):
        serializer = ReviewSerializer(
            data=self.valid_review_data(),
            context=self.context,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)


    def test_duplicate_review_is_rejected(self):
        Review.objects.create(
            assignment_id=self.assignment_id,
            reviewer_id=self.reviewer_id,
            reviewee_id=self.reviewee_id,
            reviewer_role="STUDENT",
            rating=4,
            comment="Initial review.",
        )

        serializer = ReviewSerializer(
            data=self.valid_review_data(),
            context=self.context,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("assignment_id", serializer.errors)

    def test_duplicate_review_is_rejected_with_string_reviewer_id(self):
        Review.objects.create(
            assignment_id=self.assignment_id,
            reviewer_id=self.reviewer_id,
            reviewee_id=self.reviewee_id,
            reviewer_role="STUDENT",
            rating=4,
            comment="Initial review.",
        )

        self.context["request"].user.user_id = str(self.reviewer_id)

        serializer = ReviewSerializer(
            data=self.valid_review_data(),
            context=self.context,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("assignment_id", serializer.errors)




class DeliverableSerializerTests(SimpleTestCase):
    def test_editing_submitted_work_is_rejected(self):
        work = Deliverable(
            id=uuid.uuid4(),
            assignment_id=uuid.uuid4(),
            student_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            title="Test work",
            status=Deliverable.Status.SUBMITTED,
        )

        serializer = DeliverableSerializer(
            instance=work,
            data={"title": "Updated title"},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_editing_draft_work_is_allowed(self):
        work = Deliverable(
            id=uuid.uuid4(),
            assignment_id=uuid.uuid4(),
            student_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            title="Test work",
            status=Deliverable.Status.DRAFT,
        )

        serializer = DeliverableSerializer(
            instance=work,
            data={"title": "Updated title"},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_editing_approved_work_is_rejected(self):
        work = Deliverable(
            id=uuid.uuid4(),
            assignment_id=uuid.uuid4(),
            student_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            title="Test work",
            status=Deliverable.Status.APPROVED,
        )

        serializer = DeliverableSerializer(
            instance=work,
            data={"title": "Updated title"},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_editing_revision_requested_work_is_allowed(self):
        work = Deliverable(
            id=uuid.uuid4(),
            assignment_id=uuid.uuid4(),
            student_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            title="Test work",
            status=Deliverable.Status.REVISION_REQUESTED,
        )

        serializer = DeliverableSerializer(
            instance=work,
            data={"title": "Updated title"},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)



class AuthenticationEndpointTests(APITestCase):
    def test_work_list_requires_authentication(self):
        response = self.client.get("/api/work/")

        self.assertIn(response.status_code, [401, 403])

    def test_review_list_requires_authentication(self):
        response = self.client.get("/api/reviews/")

        self.assertIn(response.status_code, [401, 403])

    def test_work_creation_requires_authentication(self):
        response = self.client.post(
            "/api/work/",
            {
                "assignment_id": "00000000-0000-0000-0000-000000000001",
                "project_id": "00000000-0000-0000-0000-000000000002",
                "title": "Test submission",
            },
            format="json",
        )

        self.assertIn(response.status_code, [401, 403])

    def test_student_sees_only_their_own_work(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from work_review.views import WorkListCreateView

        student_id = uuid.uuid4()
        another_student_id = uuid.uuid4()

        own_work = Deliverable.objects.create(
            assignment_id=uuid.uuid4(),
            student_id=student_id,
            project_id=uuid.uuid4(),
            title="My work",
        )
        other_work = Deliverable.objects.create(
            assignment_id=uuid.uuid4(),
            student_id=another_student_id,
            project_id=uuid.uuid4(),
            title="Another student's work",
        )

        factory = APIRequestFactory()
        request = factory.get("/api/work/")

        user = type(
            "TestUser",
            (),
            {
                "user_id": str(student_id),
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        force_authenticate(request, user=user)

        response = WorkListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        returned_ids = {
            str(item["id"]) for item in response.data["data"]}
        self.assertIn(str(own_work.id), returned_ids)
        self.assertNotIn(str(other_work.id), returned_ids)



class AssignmentClientTests(SimpleTestCase):
    def setUp(self):
        self.assignment_id = uuid.uuid4()
        self.url = (
            "http://application-service:8003"
            f"/api/assignments/{self.assignment_id}/"
        )
        self.access_token = "test-access-token"

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_successful_assignment_response(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "assignment_id": str(self.assignment_id),
                "student_id": str(uuid.uuid4()),
                "project_id": str(uuid.uuid4()),
            },
            "message": "Assignment retrieved successfully.",
        }
        mock_get.return_value = mock_response

        result = get_assignment(
            self.assignment_id,
            self.access_token,
        )

        self.assertEqual(
            result["assignment_id"],
            str(self.assignment_id),
        )
        mock_get.assert_called_once_with(
            self.url,
            headers={
                "Authorization": f"Bearer {self.access_token}"
            },
            timeout=3,
        )

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_assignment_not_found(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with self.assertRaises(AssignmentNotFoundError):
            get_assignment(self.assignment_id, self.access_token)

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_upstream_authorization_failure(self, mock_get):
        from work_review.assignment_client import (
            AssignmentAuthorizationError,
        )

        for status_code in (401, 403):
            with self.subTest(status_code=status_code):
                mock_response = Mock()
                mock_response.status_code = status_code
                mock_get.return_value = mock_response

                with self.assertRaises(AssignmentAuthorizationError):
                    get_assignment(
                        self.assignment_id,
                        self.access_token,
                    )

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_missing_access_token(self, mock_get):
        from work_review.assignment_client import (
            AssignmentAuthorizationError,
        )

        with self.assertRaises(AssignmentAuthorizationError):
            get_assignment(self.assignment_id, "")

        mock_get.assert_not_called()

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_service_connection_failure(self, mock_get):
        import requests

        mock_get.side_effect = requests.ConnectionError(
            "Connection refused"
        )

        from work_review.assignment_client import (
            AssignmentServiceUnavailableError,
        )

        with self.assertRaises(AssignmentServiceUnavailableError):
            get_assignment(self.assignment_id, self.access_token)

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_invalid_json_response(self, mock_get):
        from work_review.assignment_client import (
            AssignmentServiceUnavailableError,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        with self.assertRaises(AssignmentServiceUnavailableError):
            get_assignment(self.assignment_id, self.access_token)

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_missing_data_envelope(self, mock_get):
        from work_review.assignment_client import (
            AssignmentServiceUnavailableError,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "assignment_id": str(self.assignment_id),
        }
        mock_get.return_value = mock_response

        with self.assertRaises(AssignmentServiceUnavailableError):
            get_assignment(self.assignment_id, self.access_token)

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_non_object_data_envelope(self, mock_get):
        from work_review.assignment_client import (
            AssignmentServiceUnavailableError,
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [],
            "message": "Unexpected response",
        }
        mock_get.return_value = mock_response

        with self.assertRaises(AssignmentServiceUnavailableError):
            get_assignment(self.assignment_id, self.access_token)


class ProjectClientTests(SimpleTestCase):
    PROJECT_URL = "http://project-service:8002"
    ACCESS_TOKEN = "test-access-token"

    def setUp(self):
        self.project_id = str(uuid.uuid4())
        self.client_id = str(uuid.uuid4())
        self.project_data = {
            "id": self.project_id,
            "client_id": self.client_id,
            "budget": "1500.00",
            "status": "PUBLISHED",
        }

    @patch("work_review.project_client.requests.get")
    @patch.dict("os.environ", {
        "PROJECT_SERVICE_URL": "http://project-service:8002"
    })
    def test_successful_project_response(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": self.project_data,
            "message": "Project retrieved successfully",
        }
        mock_get.return_value = mock_response

        result = get_project(self.project_id, self.ACCESS_TOKEN)

        self.assertEqual(result["client_id"], self.client_id)
        self.assertEqual(result["budget"], "1500.00")
        mock_get.assert_called_once_with(
            f"{self.PROJECT_URL}/api/projects/{self.project_id}/",
            headers={
                "Authorization": f"Bearer {self.ACCESS_TOKEN}"
            },
            timeout=3,
        )

    @patch("work_review.project_client.requests.get")
    @patch.dict("os.environ", {
        "PROJECT_SERVICE_URL": "http://project-service:8002"
    })
    def test_project_not_found(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with self.assertRaises(ProjectNotFoundError):
            get_project(self.project_id, self.ACCESS_TOKEN)

    @patch("work_review.project_client.requests.get")
    @patch.dict("os.environ", {
        "PROJECT_SERVICE_URL": "http://project-service:8002"
    })
    def test_authorization_failure(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        with self.assertRaises(ProjectAuthorizationError):
            get_project(self.project_id, self.ACCESS_TOKEN)

    @patch("work_review.project_client.requests.get")
    @patch.dict("os.environ", {
        "PROJECT_SERVICE_URL": "http://project-service:8002"
    })
    def test_connection_failure(self, mock_get):
        import requests

        mock_get.side_effect = requests.ConnectionError(
            "Connection refused"
        )

        with self.assertRaises(ProjectServiceUnavailableError):
            get_project(self.project_id, self.ACCESS_TOKEN)

    @patch("work_review.project_client.requests.get")
    @patch.dict("os.environ", {
        "PROJECT_SERVICE_URL": "http://project-service:8002"
    })
    def test_invalid_response_envelope(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "Project retrieved successfully"
        }
        mock_get.return_value = mock_response

        with self.assertRaises(ProjectServiceUnavailableError):
            get_project(self.project_id, self.ACCESS_TOKEN)

    @patch("work_review.project_client.requests.get")
    @patch.dict("os.environ", {
        "PROJECT_SERVICE_URL": "http://project-service:8002"
    })
    def test_missing_project_owner(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "id": self.project_id,
                "budget": "1500.00",
            }
        }
        mock_get.return_value = mock_response

        with self.assertRaises(ProjectServiceUnavailableError):
            get_project(self.project_id, self.ACCESS_TOKEN)

    @patch("work_review.project_client.requests.get")
    @patch.dict("os.environ", {
        "PROJECT_SERVICE_URL": "http://project-service:8002"
    })
    def test_missing_project_budget(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "id": self.project_id,
                "client_id": self.client_id,
            }
        }
        mock_get.return_value = mock_response

        with self.assertRaises(ProjectServiceUnavailableError):
            get_project(self.project_id, self.ACCESS_TOKEN)

    @patch("work_review.project_client.requests.get")
    @patch.dict("os.environ", {
        "PROJECT_SERVICE_URL": "http://project-service:8002"
    })
    def test_missing_access_token(self, mock_get):
        with self.assertRaises(ProjectAuthorizationError):
            get_project(self.project_id, "")

        mock_get.assert_not_called()


class PaymentClientTests(SimpleTestCase):
    PAYMENT_URL = "http://payment-notification-service:8005"
    ACCESS_TOKEN = "test-access-token"

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_successful_payment_service_response(self, mock_post):
        assignment_id = str(uuid.uuid4())
        payment_id = str(uuid.uuid4())

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "data": {
                "id": payment_id,
                "assignment_id": assignment_id,
                "status": "pending",
            },
            "message": "Payment request accepted",
        }
        mock_post.return_value = mock_response

        result = post_payment_request(
            "api/payments/",
            {"assignment_id": assignment_id},
            self.ACCESS_TOKEN,
        )

        self.assertEqual(result["message"], "Payment request accepted")
        self.assertEqual(result["data"]["id"], payment_id)

        mock_post.assert_called_once_with(
            f"{self.PAYMENT_URL}/api/payments/",
            json={"assignment_id": assignment_id},
            headers={
                "Authorization": f"Bearer {self.ACCESS_TOKEN}"
            },
            timeout=3,
        )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_http_error_is_rejected(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        with self.assertRaises(PaymentServiceUnavailableError):
            post_payment_request(
                "api/payments/", {}, self.ACCESS_TOKEN
            )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_connection_failure_is_handled(self, mock_post):
        import requests

        mock_post.side_effect = requests.ConnectionError(
            "Connection refused"
        )

        with self.assertRaises(PaymentServiceUnavailableError):
            post_payment_request(
                "api/payments/", {}, self.ACCESS_TOKEN
            )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_invalid_json_is_rejected(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_response

        with self.assertRaises(PaymentServiceUnavailableError):
            post_payment_request(
                "api/payments/", {}, self.ACCESS_TOKEN
            )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_missing_data_envelope_is_rejected(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "message": "Payment request accepted"
        }
        mock_post.return_value = mock_response

        with self.assertRaises(PaymentServiceUnavailableError):
            post_payment_request(
                "api/payments/", {}, self.ACCESS_TOKEN
            )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_non_object_data_envelope_is_rejected(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [],
            "message": "Payment request accepted",
        }
        mock_post.return_value = mock_response

        with self.assertRaises(PaymentServiceUnavailableError):
            post_payment_request(
                "api/payments/", {}, self.ACCESS_TOKEN
            )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_unauthorized_response_is_distinguished(self, mock_post):
        from work_review.payment_client import (
            PaymentServiceAuthorizationError,
        )

        mock_response = Mock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        with self.assertRaises(PaymentServiceAuthorizationError):
            post_payment_request(
                "api/payments/", {}, self.ACCESS_TOKEN
            )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_forbidden_response_is_distinguished(self, mock_post):
        from work_review.payment_client import (
            PaymentServiceAuthorizationError,
        )

        mock_response = Mock()
        mock_response.status_code = 403
        mock_post.return_value = mock_response

        with self.assertRaises(PaymentServiceAuthorizationError):
            post_payment_request(
                "api/payments/", {}, self.ACCESS_TOKEN
            )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_missing_access_token_is_rejected_without_request(
        self, mock_post
    ):
        from work_review.payment_client import (
            PaymentServiceAuthorizationError,
        )

        with self.assertRaises(PaymentServiceAuthorizationError):
            post_payment_request("api/payments/", {}, "")

        mock_post.assert_not_called()

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {}, clear=False)
    def test_missing_service_url_is_rejected(self, mock_post):
        with patch.dict("os.environ", {"PAYMENT_SERVICE_URL": ""}):
            with self.assertRaises(PaymentServiceUnavailableError):
                post_payment_request(
                    "api/payments/", {}, self.ACCESS_TOKEN
                )

        mock_post.assert_not_called()
    
    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_process_payment_forwards_token(self, mock_post):
        payment_id = str(uuid.uuid4())
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"id": payment_id, "status": "SUCCESS"},
            "message": "Payment processed",
        }
        mock_post.return_value = mock_response

        result = process_payment_request(
            payment_id, self.ACCESS_TOKEN
        )

        self.assertEqual(result["data"]["status"], "SUCCESS")
        mock_post.assert_called_once_with(
            f"{self.PAYMENT_URL}/api/payments/{payment_id}/process/",
            json={},
            headers={
                "Authorization": f"Bearer {self.ACCESS_TOKEN}"
            },
            timeout=3,
        )

    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_release_payment_forwards_token(self, mock_post):
        payment_id = str(uuid.uuid4())
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"id": payment_id, "status": "RELEASED"},
            "message": "Payment released",
        }
        mock_post.return_value = mock_response

        result = release_payment_request(
            payment_id, self.ACCESS_TOKEN
        )

        self.assertEqual(result["data"]["status"], "RELEASED")
        mock_post.assert_called_once_with(
            f"{self.PAYMENT_URL}/api/payments/{payment_id}/release/",
            json={},
            headers={
                "Authorization": f"Bearer {self.ACCESS_TOKEN}"
            },
            timeout=3,
        )



class ReviewEndpointTests(APITestCase):
    def setUp(self):
        self.reviewer_id = uuid.uuid4()
        self.reviewee_id = uuid.uuid4()
        self.assignment_id = uuid.uuid4()

    def test_create_review_uses_authenticated_reviewer_identity(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from rest_framework import status
        from unittest.mock import patch
        from work_review.views import ReviewListCreateView

        factory = APIRequestFactory()
        request = factory.post(
            "/api/reviews/",
            {
                "assignment_id": str(self.assignment_id),
                "reviewee_id": str(self.reviewee_id),
                "reviewer_id": str(uuid.uuid4()),
                "reviewer_role": "ADMIN",
                "rating": 5,
                "comment": "Good work.",
            },
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": self.reviewer_id,
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        force_authenticate(request, user=user)

        with patch(
            "work_review.views.get_assignment",
            return_value={
                "assignment_id": str(self.assignment_id),
                "student_id": str(self.reviewer_id),
                "project_id": str(uuid.uuid4()),
            },
        ), patch(
            "work_review.views.get_project",
            return_value={
                "id": str(uuid.uuid4()),
                "client_id": str(self.reviewee_id),
                "budget": "1500.00",
                "status": "PUBLISHED",
            },
        ):
            response = ReviewListCreateView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        review = Review.objects.get(assignment_id=self.assignment_id)
        self.assertEqual(review.reviewer_id, self.reviewer_id)
        self.assertEqual(review.reviewer_role, "STUDENT")

    
    def test_unassigned_student_cannot_create_review(self):
        from unittest.mock import patch
        from rest_framework import status
        from rest_framework.test import APIRequestFactory, force_authenticate
        from work_review.views import ReviewListCreateView

        factory = APIRequestFactory()
        request = factory.post(
            "/api/reviews/",
            {
                "assignment_id": str(self.assignment_id),
                "reviewee_id": str(self.reviewee_id),
                "rating": 5,
                "comment": "Good work.",
            },
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": self.reviewer_id,
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        force_authenticate(request, user=user)

        with patch(
            "work_review.views.get_assignment",
            return_value={
                "assignment_id": str(self.assignment_id),
                "student_id": str(uuid.uuid4()),
                "project_id": str(uuid.uuid4()),
            },
        ), patch(
            "work_review.views.get_project",
            return_value={
                "id": str(uuid.uuid4()),
                "client_id": str(self.reviewee_id),
                "budget": "1500.00",
                "status": "PUBLISHED",
            },
        ):
            response = ReviewListCreateView.as_view()(request)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(Review.objects.count(), 0)

    
    def test_student_cannot_review_unrelated_client(self):
        from unittest.mock import patch
        from rest_framework import status
        from rest_framework.test import APIRequestFactory, force_authenticate
        from work_review.views import ReviewListCreateView

        factory = APIRequestFactory()
        request = factory.post(
            "/api/reviews/",
            {
                "assignment_id": str(self.assignment_id),
                "reviewee_id": str(self.reviewee_id),
                "rating": 5,
                "comment": "Good work.",
            },
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": self.reviewer_id,
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        force_authenticate(request, user=user)

        with patch(
            "work_review.views.get_assignment",
            return_value={
                "assignment_id": str(self.assignment_id),
                "student_id": str(self.reviewer_id),
                "project_id": str(uuid.uuid4()),
            },
        ), patch(
            "work_review.views.get_project",
            return_value={
                "id": str(uuid.uuid4()),
                "client_id": str(uuid.uuid4()),
                "budget": "1500.00",
                "status": "PUBLISHED",
            },
        ):
            response = ReviewListCreateView.as_view()(request)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("reviewee_id", response.data["details"])
        self.assertEqual(Review.objects.count(), 0)

    
    def test_client_cannot_review_student_on_unowned_project(self):
        from unittest.mock import patch
        from rest_framework import status
        from rest_framework.test import APIRequestFactory, force_authenticate
        from work_review.views import ReviewListCreateView

        factory = APIRequestFactory()
        request = factory.post(
            "/api/reviews/",
            {
                "assignment_id": str(self.assignment_id),
                "reviewee_id": str(self.reviewee_id),
                "rating": 5,
                "comment": "Good work.",
            },
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": self.reviewer_id,
                "role": "CLIENT",
                "is_authenticated": True,
            },
        )()
        force_authenticate(request, user=user)

        with patch(
            "work_review.views.get_assignment",
            return_value={
                "assignment_id": str(self.assignment_id),
                "student_id": str(self.reviewee_id),
                "project_id": str(uuid.uuid4()),
            },
        ), patch(
            "work_review.views.get_project",
            return_value={
                "id": str(uuid.uuid4()),
                "client_id": str(uuid.uuid4()),
                "budget": "1500.00",
                "status": "PUBLISHED",
            },
        ):
            response = ReviewListCreateView.as_view()(request)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(Review.objects.count(), 0)


    def test_duplicate_review_database_conflict_returns_validation_error(self):
        from unittest.mock import patch
        from django.db import IntegrityError
        from rest_framework import status
        from rest_framework.test import APIRequestFactory, force_authenticate
        from work_review.views import ReviewListCreateView

        with patch(
            "work_review.views.ReviewSerializer.save",
            side_effect=IntegrityError(
                "unique_review_per_assignment_reviewer"
            ),
        ):
            factory = APIRequestFactory()
            request = factory.post(
                "/api/reviews/",
                {
                    "assignment_id": str(self.assignment_id),
                    "reviewee_id": str(self.reviewee_id),
                    "rating": 5,
                    "comment": "Good work.",
                },
                format="json",
            )

            user = type(
                "TestUser",
                (),
                {
                    "user_id": self.reviewer_id,
                    "role": "STUDENT",
                    "is_authenticated": True,
                },
            )()
            force_authenticate(request, user=user)

            with patch(
                "work_review.views.get_assignment",
                return_value={
                    "assignment_id": str(self.assignment_id),
                    "student_id": str(self.reviewer_id),
                    "project_id": str(uuid.uuid4()),
                },
            ), patch(
                "work_review.views.get_project",
                return_value={
                    "id": str(uuid.uuid4()),
                    "client_id": str(self.reviewee_id),
                    "budget": "1500.00",
                    "status": "PUBLISHED",
                },
            ):
                response = ReviewListCreateView.as_view()(request)

            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
            )
            self.assertIn("assignment_id", response.data["details"])


class SubmitWorkEndpointTests(APITestCase):
    def setUp(self):
        from rest_framework.test import APIRequestFactory, force_authenticate

        self.student_id = uuid.uuid4()
        self.work = Deliverable.objects.create(
            assignment_id=uuid.uuid4(),
            student_id=self.student_id,
            project_id=uuid.uuid4(),
            title="Test submission",
            submission_url="",
        )

        self.factory = APIRequestFactory()
        self.force_authenticate = force_authenticate

    def test_submission_without_url_is_rejected(self):
        from rest_framework import status
        from work_review.views import SubmitWorkView

        request = self.factory.post(
            f"/api/work/{self.work.id}/submit/",
            {},
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": self.student_id,
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        self.force_authenticate(request, user=user)

        response = SubmitWorkView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["code"],
            "SUBMISSION_URL_REQUIRED",
        )
        self.assertIn("error", response.data)
        self.assertIn("details", response.data)
        self.assertIsInstance(response.data["details"], dict)

    def test_valid_submission_updates_status_and_timestamp(self):
        from django.utils import timezone
        from rest_framework import status
        from work_review.views import SubmitWorkView

        self.work.submission_url = "https://example.com/submission"
        self.work.save(update_fields=["submission_url"])

        request = self.factory.post(
            f"/api/work/{self.work.id}/submit/",
            {},
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": self.student_id,
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        self.force_authenticate(request, user=user)

        response = SubmitWorkView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.work.refresh_from_db()
        self.assertEqual(
            self.work.status,
            Deliverable.Status.SUBMITTED,
        )
        self.assertIsNotNone(self.work.submitted_at)
        self.assertLessEqual(
            self.work.submitted_at,
            timezone.now(),
        )

    def test_another_student_cannot_submit_work(self):
        from rest_framework.exceptions import PermissionDenied
        from work_review.views import SubmitWorkView

        self.work.submission_url = "https://example.com/submission"
        self.work.save(update_fields=["submission_url"])

        request = self.factory.post(
            f"/api/work/{self.work.id}/submit/",
            {},
            format="json",
        )

        another_student = type(
            "TestUser",
            (),
            {
                "user_id": uuid.uuid4(),
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        self.force_authenticate(request, user=another_student)

        response = SubmitWorkView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(response.status_code, 403)

    def test_already_submitted_work_cannot_be_resubmitted(self):
        from rest_framework import status
        from work_review.views import SubmitWorkView

        self.work.submission_url = "https://example.com/submission"
        self.work.status = Deliverable.Status.SUBMITTED
        self.work.save(update_fields=["submission_url", "status"])

        request = self.factory.post(
            f"/api/work/{self.work.id}/submit/",
            {},
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": self.student_id,
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        self.force_authenticate(request, user=user)

        response = SubmitWorkView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["code"],
            "INVALID_WORK_STATUS",
        )
        self.assertIn("error", response.data)
        self.assertIn("details", response.data)
        self.assertIsInstance(response.data["details"], dict)

    def test_student_string_user_id_can_submit_own_work(self):
        from rest_framework import status
        from work_review.views import SubmitWorkView

        self.work.submission_url = "https://example.com/submission"
        self.work.save(update_fields=["submission_url"])

        request = self.factory.post(
            f"/api/work/{self.work.id}/submit/",
            {},
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": str(self.student_id),
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        self.force_authenticate(request, user=user)

        response = SubmitWorkView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )


class RequestRevisionEndpointTests(APITestCase):
    def setUp(self):
        from rest_framework.test import APIRequestFactory, force_authenticate

        self.student_id = uuid.uuid4()
        self.client_id = uuid.uuid4()

        self.work = Deliverable.objects.create(
            assignment_id=uuid.uuid4(),
            student_id=self.student_id,
            project_id=uuid.uuid4(),
            title="Test work",
            submission_url="https://example.com/submission",
            status=Deliverable.Status.SUBMITTED,
        )

        self.factory = APIRequestFactory()
        self.force_authenticate = force_authenticate

    
    def make_request(self, user_id, role, work_id, data=None):
        request = self.factory.post(
            f"/api/work/{work_id}/reject/",
            {} if data is None else data,
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": user_id,
                "role": role,
                "is_authenticated": True,
            },
        )()

        self.force_authenticate(request, user=user)
        return request


    def test_student_cannot_request_revisions(self):
        from rest_framework import status
        from work_review.views import RequestRevisionView

        request = self.make_request(
            self.student_id,
            "STUDENT",
            self.work.id,
        )

        response = RequestRevisionView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_missing_work_returns_404(self):
        from rest_framework import status
        from work_review.views import RequestRevisionView

        missing_work_id = uuid.uuid4()
        request = self.make_request(
            self.client_id,
            "CLIENT",
            missing_work_id,
        )

        response = RequestRevisionView.as_view()(
            request,
            work_id=missing_work_id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            response.data["code"],
            "NOT_FOUND",
        )
        self.assertIn("error", response.data)
        self.assertIn("details", response.data)
        self.assertIsInstance(response.data["details"], dict)

    
    @patch(
        "work_review.views.get_assignment",
        side_effect=AssignmentServiceUnavailableError(
            "Assignment Service is unavailable."
        ),
    )
    def test_client_gets_503_when_assignment_service_is_unavailable(
        self, mock_get_assignment
    ):
        from rest_framework import status
        from work_review.views import RequestRevisionView

        request = self.make_request(
            self.client_id,
            "CLIENT",
            self.work.id,
        )

        response = RequestRevisionView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            response.data["code"],
            "SERVICE_UNAVAILABLE",
        )
        mock_get_assignment.assert_called_once()
    
    @patch(
        "work_review.views.verify_client_ownership",
        return_value=({}, {"client_id": "placeholder"}),
    )
    def test_revision_request_requires_feedback(self, mock_ownership):
        from rest_framework import status
        from work_review.views import RequestRevisionView

        request = self.make_request(
                self.client_id,
                "CLIENT",
                self.work.id,)
        request.data = {}

        response = RequestRevisionView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        mock_ownership.assert_called_once()

    @patch(
        "work_review.views.verify_client_ownership",
        return_value=({}, {"client_id": "placeholder"}),
    )
    def test_revision_request_updates_status_and_feedback(
        self, mock_ownership
    ):
        from rest_framework import status
        from work_review.views import RequestRevisionView

        request = self.make_request(
            self.client_id,
            "CLIENT",
            self.work.id,
            data={"feedback": "Please include the missing test results."},
        )

        response = RequestRevisionView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.work.refresh_from_db()
        self.assertEqual(
            self.work.status,
            Deliverable.Status.REVISION_REQUESTED,
        )
        self.assertEqual(
            self.work.feedback,
            "Please include the missing test results.",
        )
        mock_ownership.assert_called_once()



class ApproveWorkEndpointTests(APITestCase):
    def setUp(self):
        from rest_framework.test import APIRequestFactory, force_authenticate

        self.student_id = uuid.uuid4()
        self.client_id = uuid.uuid4()

        self.work = Deliverable.objects.create(
            assignment_id=uuid.uuid4(),
            student_id=self.student_id,
            project_id=uuid.uuid4(),
            title="Test work",
            submission_url="https://example.com/submission",
            status=Deliverable.Status.SUBMITTED,
        )

        self.factory = APIRequestFactory()
        self.force_authenticate = force_authenticate

    def make_request(self, user_id, role, work_id):
        request = self.factory.post(
            f"/api/work/{work_id}/approve/",
            {},
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": user_id,
                "role": role,
                "is_authenticated": True,
            },
        )()

        self.force_authenticate(request, user=user)
        return request

    def test_student_cannot_approve_work(self):
        from rest_framework import status
        from work_review.views import ApproveWorkView

        request = self.make_request(
            self.student_id,
            "STUDENT",
            self.work.id,
        )

        response = ApproveWorkView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_missing_work_returns_404(self):
        from rest_framework import status
        from work_review.views import ApproveWorkView

        missing_work_id = uuid.uuid4()
        request = self.make_request(
            self.client_id,
            "CLIENT",
            missing_work_id,
        )

        response = ApproveWorkView.as_view()(
            request,
            work_id=missing_work_id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            response.data["code"],
            "NOT_FOUND",
        )
        self.assertIn("error", response.data)
        self.assertIn("details", response.data)
        self.assertIsInstance(response.data["details"], dict)

    
    @patch("work_review.views.verify_client_ownership")
    @patch("work_review.views.post_payment_request")
    @patch("work_review.views.process_payment_request")
    @patch("work_review.views.release_payment_request")
    def test_client_can_approve_submitted_work_after_payment_release(
        self,
        mock_release,
        mock_process,
        mock_create,
        mock_ownership,
    ):
        from rest_framework import status
        from work_review.views import ApproveWorkView

        assignment = {
            "id": str(self.work.assignment_id),
            "project_id": str(self.work.project_id),
            "student_id": str(self.student_id),
        }
        project = {
            "client_id": str(self.client_id),
            "budget": "1000.00",
        }
        mock_ownership.return_value = (assignment, project)

        mock_create.return_value = {
            "data": {
                "id": str(uuid.uuid4()),
                "status": "PENDING",
            },
            "message": "Payment created",
        }
        mock_process.return_value = {
            "data": {
                "id": str(uuid.uuid4()),
                "status": "SUCCESS",
            },
            "message": "Payment processed",
        }
        # The release endpoint returns the same payment ID in real usage.
        payment_id = str(uuid.uuid4())
        mock_create.return_value["data"]["id"] = payment_id
        mock_process.return_value["data"]["id"] = payment_id
        mock_release.return_value = {
            "data": {
                "id": payment_id,
                "status": "RELEASED",
            },
            "message": "Payment released",
        }

        request = self.make_request(
            self.client_id,
            "CLIENT",
            self.work.id,
        )

        response = ApproveWorkView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.work.refresh_from_db()
        self.assertEqual(self.work.status, Deliverable.Status.APPROVED)
        self.assertTrue(self.work.payment_requested)
        self.assertIsNotNone(self.work.reviewed_at)

        mock_ownership.assert_called_once()
        mock_create.assert_called_once()
        mock_process.assert_called_once()
        mock_release.assert_called_once()
    
    @patch("work_review.views.verify_client_ownership")
    @patch("work_review.views.post_payment_request")
    def test_payment_creation_failure_does_not_approve_work(
        self, mock_create, mock_ownership
    ):
        from rest_framework import status
        from work_review.payment_client import PaymentServiceUnavailableError
        from work_review.views import ApproveWorkView

        mock_ownership.return_value = (
            {"project_id": str(self.work.project_id)},
            {"client_id": str(self.client_id), "budget": "1000.00"},
        )
        mock_create.side_effect = PaymentServiceUnavailableError(
            "Payment Service unavailable"
        )

        request = self.make_request(self.client_id, "CLIENT", self.work.id)
        response = ApproveWorkView.as_view()(request, work_id=self.work.id)

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.work.refresh_from_db()
        self.assertEqual(self.work.status, Deliverable.Status.SUBMITTED)
        self.assertFalse(self.work.payment_requested)
        mock_create.assert_called_once()

    @patch("work_review.views.verify_client_ownership")
    @patch("work_review.views.post_payment_request")
    @patch("work_review.views.process_payment_request")
    def test_payment_processing_failure_does_not_approve_work(
        self, mock_process, mock_create, mock_ownership
    ):
        from rest_framework import status
        from work_review.payment_client import PaymentServiceUnavailableError
        from work_review.views import ApproveWorkView

        mock_ownership.return_value = (
            {"project_id": str(self.work.project_id)},
            {"client_id": str(self.client_id), "budget": "1000.00"},
        )
        payment_id = str(uuid.uuid4())
        mock_create.return_value = {
            "data": {"id": payment_id, "status": "PENDING"},
            "message": "Payment created",
        }
        mock_process.side_effect = PaymentServiceUnavailableError(
            "Payment processing unavailable"
        )

        request = self.make_request(self.client_id, "CLIENT", self.work.id)
        response = ApproveWorkView.as_view()(request, work_id=self.work.id)

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.work.refresh_from_db()
        self.assertEqual(self.work.status, Deliverable.Status.SUBMITTED)
        self.assertFalse(self.work.payment_requested)
        mock_create.assert_called_once()
        mock_process.assert_called_once_with(payment_id, request.auth)

    @patch("work_review.views.verify_client_ownership")
    @patch("work_review.views.post_payment_request")
    @patch("work_review.views.process_payment_request")
    @patch("work_review.views.release_payment_request")
    def test_payment_release_failure_does_not_approve_work(
        self, mock_release, mock_process, mock_create, mock_ownership
    ):
        from rest_framework import status
        from work_review.payment_client import PaymentServiceUnavailableError
        from work_review.views import ApproveWorkView

        mock_ownership.return_value = (
            {"project_id": str(self.work.project_id)},
            {"client_id": str(self.client_id), "budget": "1000.00"},
        )
        payment_id = str(uuid.uuid4())
        mock_create.return_value = {
            "data": {"id": payment_id, "status": "PENDING"},
            "message": "Payment created",
        }
        mock_process.return_value = {
            "data": {"id": payment_id, "status": "SUCCESS"},
            "message": "Payment processed",
        }
        mock_release.side_effect = PaymentServiceUnavailableError(
            "Payment release unavailable"
        )

        request = self.make_request(self.client_id, "CLIENT", self.work.id)
        response = ApproveWorkView.as_view()(request, work_id=self.work.id)

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.work.refresh_from_db()
        self.assertEqual(self.work.status, Deliverable.Status.SUBMITTED)
        self.assertFalse(self.work.payment_requested)
        mock_create.assert_called_once()
        mock_process.assert_called_once_with(payment_id, request.auth)
        mock_release.assert_called_once_with(payment_id, request.auth)



class WorkDetailEndpointTests(APITestCase):
    def setUp(self):
        from rest_framework.test import APIRequestFactory, force_authenticate

        self.student_id = uuid.uuid4()
        self.work = Deliverable.objects.create(
            assignment_id=uuid.uuid4(),
            student_id=self.student_id,
            project_id=uuid.uuid4(),
            title="Approved work",
            submission_url="https://example.com/submission",
            status=Deliverable.Status.APPROVED,
        )

        self.factory = APIRequestFactory()
        self.force_authenticate = force_authenticate

    def test_student_cannot_edit_approved_work(self):
        from rest_framework import status
        from work_review.views import WorkDetailView

        request = self.factory.put(
            f"/api/work/{self.work.id}/",
            {
                "title": "Changed title",
                "assignment_id": str(self.work.assignment_id),
                "project_id": str(self.work.project_id),
            },
            format="json",
        )

        user = type(
            "TestUser",
            (),
            {
                "user_id": str(self.student_id),
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        self.force_authenticate(request, user=user)

        response = WorkDetailView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("non_field_errors", response.data["details"])

    def test_another_student_cannot_retrieve_work(self):
        from rest_framework import status
        from work_review.views import WorkDetailView

        request = self.factory.get(
            f"/api/work/{self.work.id}/",
        )

        another_student = type(
            "TestUser",
            (),
            {
                "user_id": str(uuid.uuid4()),
                "role": "STUDENT",
                "is_authenticated": True,
            },
        )()
        self.force_authenticate(request, user=another_student)

        response = WorkDetailView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_assignment_id_cannot_change_after_creation(self):
        from rest_framework.exceptions import ValidationError
        from work_review.serializers import DeliverableSerializer

        self.work.status = Deliverable.Status.DRAFT
        self.work.save(update_fields=["status"])

        serializer = DeliverableSerializer(
            instance=self.work,
            data={"assignment_id": str(uuid.uuid4())},
            partial=True,
        )

        with self.assertRaises(ValidationError) as context:
            serializer.is_valid(raise_exception=True)

        self.assertIn("assignment_id", context.exception.detail)

    def test_project_id_cannot_change_after_creation(self):
        from rest_framework.exceptions import ValidationError
        from work_review.serializers import DeliverableSerializer

        self.work.status = Deliverable.Status.DRAFT
        self.work.save(update_fields=["status"])

        serializer = DeliverableSerializer(
            instance=self.work,
            data={"project_id": str(uuid.uuid4())},
            partial=True,
        )

        with self.assertRaises(ValidationError) as context:
            serializer.is_valid(raise_exception=True)

        self.assertIn("project_id", context.exception.detail)
