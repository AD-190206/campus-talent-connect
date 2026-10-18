import os
from uuid import uuid4
from unittest.mock import Mock, patch

import jwt
import requests
from .services import PaymentServiceError, process_payment, release_payment
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .integrations import UpstreamServiceError, get_upstream_data
from .models import Payment, Notification


@override_settings(MOCK_PAYMENT_ENABLED=True)
class PaymentNotificationAPITests(TestCase):
    def setUp(self):
        self.client = self.authenticated_client()
        self.payload = {
            "assignment_id": str(uuid4()),
            "payer_id": self.user_id,
            "payee_id": str(uuid4()),
            "amount": "1500.00",
            "idempotency_key": "test-payment-key-001",
        }
        self.assignment_patcher = patch(
            "payments_notifications.views.get_assignment",
            return_value={
                "project_id": str(uuid4()),
                "student_id": self.payload["payee_id"],
            },
        )
        self.assignment_patcher.start()
        self.addCleanup(self.assignment_patcher.stop)

        self.project_patcher = patch(
            "payments_notifications.views.get_project",
            return_value={
                "client_id": self.user_id,
                "budget": "5000.00",
            },
        )
        self.project_patcher.start()
        self.addCleanup(self.project_patcher.stop)

    def create_payment(self, payload=None):
        return self.client.post(
            "/api/payments/",
            payload or self.payload,
            format="json",
        )

    def test_payment_rejects_assignment_student_mismatch(self):
        self.assignment_patcher.stop()
        self.assignment_patcher = patch(
            "payments_notifications.views.get_assignment",
            return_value={
                "project_id": str(uuid4()),
                "student_id": str(uuid4()),
            },
        )
        self.assignment_patcher.start()

        response = self.create_payment()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["code"],
            "PAYEE_ASSIGNMENT_MISMATCH",
        )
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_rejects_project_client_mismatch(self):
        self.project_patcher.stop()
        self.project_patcher = patch(
            "payments_notifications.views.get_project",
            return_value={
                "client_id": str(uuid4()),
                "budget": "5000.00",
            },
        )
        self.project_patcher.start()

        response = self.create_payment()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["code"],
            "PAYER_PROJECT_MISMATCH",
        )
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_exceeding_project_budget_is_rejected(self):
        self.project_patcher.stop()
        self.project_patcher = patch(
            "payments_notifications.views.get_project",
            return_value={
                "client_id": self.user_id,
                "budget": "1000.00",
            },
        )
        self.project_patcher.start()

        response = self.create_payment()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["code"],
            "PAYMENT_EXCEEDS_PROJECT_BUDGET",
        )
        self.assertEqual(Payment.objects.count(), 0)

    def test_payment_rejects_invalid_project_budget(self):
        self.project_patcher.stop()
        self.project_patcher = patch(
            "payments_notifications.views.get_project",
            return_value={
                "client_id": self.user_id,
                "budget": "not-a-number",
            },
        )
        self.project_patcher.start()

        response = self.create_payment()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.data["code"],
            "UPSTREAM_INVALID_RESPONSE",
        )
        self.assertEqual(Payment.objects.count(), 0)

    def test_create_payment_starts_pending(self):
        response = self.create_payment()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["status"], "PENDING")
        self.assertEqual(Payment.objects.count(), 1)

    def test_duplicate_key_reuses_existing_payment(self):
        first = self.create_payment()
        second = self.create_payment()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            first.data["data"]["id"],
            second.data["data"]["id"],
        )
        self.assertEqual(Payment.objects.count(), 1)

    def test_duplicate_key_with_different_amount_returns_conflict(self):
        self.create_payment()

        changed_payload = {
            **self.payload,
            "amount": "2500.00",
        }
        response = self.create_payment(changed_payload)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data["code"],
            "IDEMPOTENCY_KEY_CONFLICT",
        )
        self.assertEqual(Payment.objects.count(), 1)

    def test_successful_processing_creates_notifications(self):
        response = self.create_payment()
        payment_id = response.data["data"]["id"]

        processed = self.client.post(
            f"/api/payments/{payment_id}/process/",
            {"simulate_failure": False},
            format="json",
        )

        self.assertEqual(processed.status_code, 200)
        self.assertEqual(processed.data["data"]["status"], "SUCCESS")
        self.assertTrue(
            processed.data["data"]["transaction_id"].startswith("MOCK-")
        )
        self.assertEqual(Notification.objects.count(), 2)

    def test_simulated_failure_creates_notifications(self):
        response = self.create_payment()
        payment_id = response.data["data"]["id"]

        processed = self.client.post(
            f"/api/payments/{payment_id}/process/",
            {"simulate_failure": True},
            format="json",
        )

        self.assertEqual(processed.status_code, 200)
        self.assertEqual(processed.data["data"]["status"], "FAILED")
        self.assertEqual(Notification.objects.count(), 2)

    def test_notification_creation_and_listing(self):
        payload = {
            "user_id": self.user_id,
            "type": "IN_APP",
            "event": "TEST_EVENT",
            "message": "Test notification",
        }

        created = self.client.post(
            "/api/notifications/",
            payload,
            format="json",
        )
        listed = self.client.get("/api/notifications/")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data["data"]), 1)
        self.assertEqual(
            listed.data["data"][0]["message"],
            "Test notification",
        )

    def test_zero_amount_is_rejected(self):
        payload = {
            **self.payload,
            "idempotency_key": "zero-amount-test",
            "amount": "0.00",
        }

        response = self.create_payment(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Payment.objects.count(), 0)

    def test_validation_error_includes_details_field(self):
        payload = {
            **self.payload,
            "idempotency_key": "zero-amount-details-test",
            "amount": "0.00",
        }

        response = self.create_payment(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.assertEqual(response.data["error"], "Request validation failed.")
        self.assertIn("details", response.data)
        self.assertIn("amount", response.data["details"])

    def test_payment_history_only_returns_payments_involving_current_user(self):
        own_payload = {
            **self.payload,
            "payer_id": self.user_id,
            "idempotency_key": "own-payment",
        }
        other_payload = {
            **self.payload,
            "payer_id": str(uuid4()),
            "payee_id": str(uuid4()),
            "idempotency_key": "other-payment",
        }

        self.create_payment(own_payload)
        self.create_payment(other_payload)

        response = self.client.get("/api/payments/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(
            response.data["data"][0]["payer_id"],
            self.user_id,
        )

    def test_payment_detail_is_not_visible_to_unrelated_user(self):
        other_user_id = str(uuid4())

        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=other_user_id,
            payee_id=str(uuid4()),
            amount="1500.00",
            fee="0.00",
            idempotency_key="unrelated-payment",
        )

        response = self.client.get(
            f"/api/payments/{payment.id}/"
        )

        self.assertEqual(response.status_code, 404)

    def test_payment_creation_rejects_another_users_as_payer(self):
        payload = {
            **self.payload,
            "payer_id": str(uuid4()),
            "idempotency_key": "forged-payer-test",
        }

        response = self.create_payment(payload)

        self.assertIn(response.status_code, [400, 403])
        self.assertEqual(Payment.objects.count(), 0)

    def test_unrelated_user_cannot_process_payment(self):
        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=str(uuid4()),
            payee_id=str(uuid4()),
            amount="1500.00",
            fee="0.00",
            idempotency_key="unrelated-process-test",
        )

        response = self.client.post(
            f"/api/payments/{payment.id}/process/",
            {"simulate_failure": False},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_successful_payment_can_be_released(self):
        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=self.user_id,
            payee_id=str(uuid4()),
            amount="1500.00",
            fee="0.00",
            status=Payment.Status.SUCCESS,
            idempotency_key="successful-release-test",
        )

        response = self.client.post(
            f"/api/payments/{payment.id}/release/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], "RELEASED")

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.RELEASED)

    def test_repeated_release_keeps_payment_released(self):
        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=self.user_id,
            payee_id=str(uuid4()),
            amount="1500.00",
            fee="0.00",
            status=Payment.Status.SUCCESS,
            idempotency_key="repeated-release-test",
        )

        first = self.client.post(
            f"/api/payments/{payment.id}/release/",
            {},
            format="json",
        )
        second = self.client.post(
            f"/api/payments/{payment.id}/release/",
            {},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["data"]["status"], "RELEASED")

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.RELEASED)

    def test_unrelated_user_cannot_release_payment(self):
        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=str(uuid4()),
            payee_id=str(uuid4()),
            amount="1500.00",
            fee="0.00",
            status=Payment.Status.SUCCESS,
            idempotency_key="unrelated-release-test",
        )

        response = self.client.post(
            f"/api/payments/{payment.id}/release/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)

    @override_settings(MOCK_PAYMENT_ENABLED=False)
    def test_mock_payment_processing_is_disabled(self):
        response = self.create_payment()
        payment_id = response.data["data"]["id"]
        payment = Payment.objects.get(id=payment_id)

        with self.assertRaises(PaymentServiceError):
            process_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_pending_payment_cannot_be_released(self):
        response = self.create_payment()
        payment_id = response.data["data"]["id"]
        payment = Payment.objects.get(id=payment_id)

        with self.assertRaises(PaymentServiceError):
            release_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def authenticated_client(self):
        import time

        secret = os.getenv("JWT_SECRET_KEY")
        self.user_id = str(uuid4())

        now = int(time.time())
        token = jwt.encode(
            {
                "user_id": self.user_id,
                "role": "CLIENT",
                "iat": now,
                "exp": now + 300,
                "token_type": "access",
            },
            secret,
            algorithm="HS256",
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    def test_user_cannot_create_notification_for_another_user(self):
        other_user_id = str(uuid4())

        response = self.client.post(
            "/api/notifications/",
            {
                "user_id": other_user_id,
                "type": "IN_APP",
                "event": "TEST_EVENT",
                "message": "Test notification",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["code"],
            "NOTIFICATION_USER_MISMATCH",
        )

    def test_payment_history_returns_pagination_metadata(self):
        self.create_payment()

        response = self.client.get("/api/payments/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pagination"]["page"], 1)
        self.assertEqual(response.data["pagination"]["page_size"], 20)
        self.assertEqual(response.data["pagination"]["total"], 1)
        self.assertEqual(response.data["pagination"]["total_pages"], 1)

    def test_payment_history_rejects_invalid_page_size(self):
        response = self.client.get("/api/payments/?page_size=101")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "INVALID_PAGINATION")
        self.assertIn("details", response.data)

    def test_notification_list_returns_pagination_metadata(self):
        payload = {
            "user_id": self.user_id,
            "type": "IN_APP",
            "message": "Your payment has been processed.",
        }

        create_response = self.client.post(
            "/api/notifications/",
            payload,
            format="json",
        )
        self.assertEqual(
            create_response.status_code,
            201,
            f"Notification creation failed: {create_response.data}",
        )

        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("pagination", response.data)
        self.assertEqual(response.data["pagination"]["page"], 1)
        self.assertEqual(response.data["pagination"]["page_size"], 20)
        self.assertEqual(response.data["pagination"]["total"], 1)
        self.assertEqual(response.data["pagination"]["total_pages"], 1)

    def test_notification_list_rejects_invalid_page_size(self):
        response = self.client.get("/api/notifications/?page_size=101")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["code"],
            "INVALID_PAGINATION",
        )
        self.assertIn("details", response.data)

    def test_payment_history_requires_authentication(self):
        client = APIClient()

        response = client.get("/api/payments/")

        self.assertEqual(response.status_code, 401)

    def test_payment_history_rejects_invalid_token(self):
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION="Bearer invalid-token"
        )

        response = client.get("/api/payments/")

        self.assertEqual(response.status_code, 401)

    def test_payment_history_rejects_missing_required_claims(self):
        import time

        secret = os.getenv("JWT_SECRET_KEY")
        token = jwt.encode(
            {
                "user_id": str(uuid4()),
                "role": "CLIENT",
                "iat": int(time.time()),
                "exp": int(time.time()) + 300,
                # token_type is deliberately missing
            },
            secret,
            algorithm="HS256",
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = client.get("/api/payments/")

        self.assertEqual(response.status_code, 401)

    def test_payment_history_rejects_invalid_role(self):
        import time

        secret = os.getenv("JWT_SECRET_KEY")
        now = int(time.time())
        token = jwt.encode(
            {
                "user_id": str(uuid4()),
                "role": "SUPERUSER",
                "iat": now,
                "exp": now + 300,
                "token_type": "access",
            },
            secret,
            algorithm="HS256",
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = client.get("/api/payments/")

        self.assertEqual(response.status_code, 401)

    def test_payment_history_rejects_refresh_token(self):
        import time

        secret = os.getenv("JWT_SECRET_KEY")
        now = int(time.time())
        token = jwt.encode(
            {
                "user_id": str(uuid4()),
                "role": "CLIENT",
                "iat": now,
                "exp": now + 300,
                "token_type": "refresh",
            },
            secret,
            algorithm="HS256",
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = client.get("/api/payments/")

        self.assertEqual(response.status_code, 401)


class UpstreamIntegrationTests(TestCase):
    def setUp(self):
        self.base_url = "http://example-service:8000"
        self.path = "/api/assignments/test-id/"
        self.authorization = "Bearer test-token"

    @patch("payments_notifications.integrations.requests.get")
    def test_valid_response_returns_data(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {
            "data": {"id": "test-id"},
            "message": "Assignment retrieved successfully",
        }
        mock_get.return_value = mock_response

        result = get_upstream_data(
            self.base_url, self.path, self.authorization
        )

        self.assertEqual(result, {"id": "test-id"})
        mock_get.assert_called_once()

    @patch("payments_notifications.integrations.requests.get")
    def test_invalid_json_raises_error(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        with self.assertRaises(UpstreamServiceError) as context:
            get_upstream_data(
                self.base_url, self.path, self.authorization
            )

        self.assertEqual(
            context.exception.code, "UPSTREAM_INVALID_RESPONSE"
        )
        self.assertEqual(context.exception.http_status, 502)

    @patch("payments_notifications.integrations.requests.get")
    def test_missing_message_rejects_response(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.json.return_value = {"data": {"id": "test-id"}}
        mock_get.return_value = mock_response

        with self.assertRaises(UpstreamServiceError) as context:
            get_upstream_data(
                self.base_url, self.path, self.authorization
            )

        self.assertEqual(
            context.exception.code, "UPSTREAM_INVALID_RESPONSE"
        )

    @patch("payments_notifications.integrations.requests.get")
    def test_timeout_raises_gateway_timeout(self, mock_get):
        mock_get.side_effect = requests.Timeout("Request timed out")

        with self.assertRaises(UpstreamServiceError) as context:
            get_upstream_data(
                self.base_url, self.path, self.authorization
            )

        self.assertEqual(context.exception.code, "UPSTREAM_TIMEOUT")
        self.assertEqual(context.exception.http_status, 504)

    @patch("payments_notifications.integrations.requests.get")
    def test_connection_error_reports_unavailable(self, mock_get):
        mock_get.side_effect = requests.ConnectionError(
            "Connection refused"
        )

        with self.assertRaises(UpstreamServiceError) as context:
            get_upstream_data(
                self.base_url, self.path, self.authorization
            )

        self.assertEqual(
            context.exception.code, "UPSTREAM_UNAVAILABLE"
        )
        self.assertEqual(context.exception.http_status, 503)

    def test_missing_service_url_reports_not_configured(self):
        with self.assertRaises(UpstreamServiceError) as context:
            get_upstream_data("", self.path, self.authorization)

        self.assertEqual(
            context.exception.code, "UPSTREAM_NOT_CONFIGURED"
        )
        self.assertEqual(context.exception.http_status, 503)

    def test_missing_authorization_is_rejected(self):
        with self.assertRaises(UpstreamServiceError) as context:
            get_upstream_data(self.base_url, self.path, "")

        self.assertEqual(
            context.exception.code, "UPSTREAM_AUTHORIZATION_MISSING"
        )
        self.assertEqual(context.exception.http_status, 401)
