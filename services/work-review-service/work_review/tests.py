from django.test import TestCase
import uuid
from unittest.mock import Mock, patch

from work_review.assignment_client import (
    get_assignment,
    AssignmentNotFoundError,
    AssignmentServiceUnavailableError,
)
from work_review.payment_client import (
    post_payment_request,
    PaymentServiceUnavailableError,
)



from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from work_review.models import Deliverable, Review
from work_review.serializers import DeliverableSerializer, ReviewSerializer
from rest_framework.test import APITestCase

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
            str(item["id"]) for item in response.data
        }
        self.assertIn(str(own_work.id), returned_ids)
        self.assertNotIn(str(other_work.id), returned_ids)


class AssignmentClientTests(SimpleTestCase):
    def setUp(self):
        self.assignment_id = uuid.uuid4()
        self.url = (
            "http://application-service:8003"
            f"/api/assignments/{self.assignment_id}/"
        )

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_successful_assignment_response(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "assignment_id": str(self.assignment_id),
            "student_id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
        }
        mock_get.return_value = mock_response

        result = get_assignment(self.assignment_id)

        self.assertEqual(result["assignment_id"], str(self.assignment_id))
        mock_get.assert_called_once_with(self.url, timeout=3)

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_assignment_not_found(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with self.assertRaises(AssignmentNotFoundError):
            get_assignment(self.assignment_id)

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_service_connection_failure(self, mock_get):
        import requests

        mock_get.side_effect = requests.ConnectionError(
            "Connection refused"
        )

        with self.assertRaises(AssignmentServiceUnavailableError):
            get_assignment(self.assignment_id)

    @patch("work_review.assignment_client.requests.get")
    @patch.dict("os.environ", {
        "APPLICATION_SERVICE_URL": "http://application-service:8003"
    })
    def test_invalid_json_response(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        with self.assertRaises(AssignmentServiceUnavailableError):
            get_assignment(self.assignment_id)

class PaymentClientTests(SimpleTestCase):
    @patch("work_review.payment_client.requests.post")
    @patch.dict("os.environ", {
        "PAYMENT_SERVICE_URL": "http://payment-notification-service:8005"
    })
    def test_successful_payment_service_response(self, mock_post):
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "message": "Payment request accepted"
        }
        mock_post.return_value = mock_response

        result = post_payment_request(
            "api/payments/",
            {"assignment_id": str(uuid.uuid4())},
        )

        self.assertEqual(result["message"], "Payment request accepted")
        mock_post.assert_called_once_with(
            "http://payment-notification-service:8005/api/payments/",
            json={"assignment_id": mock_post.call_args.kwargs["json"]["assignment_id"]},
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
            post_payment_request("api/payments/", {})

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
            post_payment_request("api/payments/", {})

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
            post_payment_request("api/payments/", {})


class ReviewEndpointTests(APITestCase):
    def setUp(self):
        self.reviewer_id = uuid.uuid4()
        self.reviewee_id = uuid.uuid4()
        self.assignment_id = uuid.uuid4()

    def test_create_review_uses_authenticated_reviewer_identity(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from rest_framework import status
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

        response = ReviewListCreateView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        review = Review.objects.get(assignment_id=self.assignment_id)
        self.assertEqual(review.reviewer_id, self.reviewer_id)
        self.assertEqual(review.reviewer_role, "STUDENT")


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

    def make_request(self, user_id, role, work_id):
        request = self.factory.post(
            f"/api/work/{work_id}/reject/",
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
            "WORK_NOT_FOUND",
        )

    def test_client_gets_503_until_ownership_verification_is_configured(self):
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
            "OWNERSHIP_VERIFICATION_UNAVAILABLE",
        )


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
            "WORK_NOT_FOUND",
        )

    def test_client_gets_503_until_ownership_verification_is_configured(self):
        from rest_framework import status
        from work_review.views import ApproveWorkView

        request = self.make_request(
            self.client_id,
            "CLIENT",
            self.work.id,
        )

        response = ApproveWorkView.as_view()(
            request,
            work_id=self.work.id,
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(
            response.data["code"],
            "OWNERSHIP_VERIFICATION_UNAVAILABLE",
        )

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
            {"title": "Changed title"},
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
        self.assertIn("non_field_errors", response.data)

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
