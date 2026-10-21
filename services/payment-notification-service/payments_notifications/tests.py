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

        self.work_patcher = patch(
            "payments_notifications.views.get_work_for_assignment",
            return_value=[{"status": "SUBMITTED"}],
        )
        self.work_lookup = self.work_patcher.start()
        self.addCleanup(self.work_patcher.stop)

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

    def test_payment_amount_comes_from_project_budget(self):
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

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["amount"], "1000.00")
        self.assertEqual(Payment.objects.count(), 1)

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
        first = self.create_payment()
        self.assertEqual(first.status_code, 201)

        # The client-supplied amount is ignored; the project budget
        # determines the amount, so the same request remains idempotent.
        changed_payload = {
            **self.payload,
            "amount": "2500.00",
        }
        response = self.create_payment(changed_payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            first.data["data"]["id"],
            response.data["data"]["id"],
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

    def test_reprocessing_successful_payment_does_not_duplicate_notifications(self):
        response = self.create_payment()
        payment_id = response.data["data"]["id"]

        first_process = self.client.post(
            f"/api/payments/{payment_id}/process/",
            {"simulate_failure": False},
            format="json",
        )
        self.assertEqual(first_process.status_code, 200)
        self.assertEqual(Notification.objects.count(), 2)

        second_process = self.client.post(
            f"/api/payments/{payment_id}/process/",
            {"simulate_failure": False},
            format="json",
        )
        self.assertEqual(second_process.status_code, 200)
        self.assertEqual(second_process.data["data"]["status"], "SUCCESS")
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

    def test_reprocessing_failed_payment_does_not_duplicate_notifications(self):
        response = self.create_payment()
        payment_id = response.data["data"]["id"]

        first_process = self.client.post(
            f"/api/payments/{payment_id}/process/",
            {"simulate_failure": True},
            format="json",
        )

        self.assertEqual(first_process.status_code, 200)
        self.assertEqual(
            first_process.data["data"]["status"],
            "FAILED",
        )
        self.assertEqual(Notification.objects.count(), 2)

        second_process = self.client.post(
            f"/api/payments/{payment_id}/process/",
            {"simulate_failure": False},
            format="json",
        )

        self.assertEqual(second_process.status_code, 200)
        self.assertEqual(
            second_process.data["data"]["status"],
            "FAILED",
        )
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

    def test_notification_rejects_blank_message(self):
        response = self.client.post(
            "/api/notifications/",
            {
                "user_id": self.user_id,
                "type": "IN_APP",
                "event": "TEST_EVENT",
                "message": "   ",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_notification_trims_message_whitespace(self):
        response = self.client.post(
            "/api/notifications/",
            {
                "user_id": self.user_id,
                "type": "IN_APP",
                "event": "TEST_EVENT",
                "message": "  Test notification  ",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["data"]["message"],
            "Test notification",
        )

    def test_missing_idempotency_key_is_rejected(self):
        payload = {
            "assignment_id": self.payload["assignment_id"],
            "payee_id": self.payload["payee_id"],
        }

        response = self.create_payment(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.assertIn("idempotency_key", response.data["details"]["fields"])
        self.assertEqual(Payment.objects.count(), 0)

    def test_validation_error_includes_details_field(self):
        payload = {
            "assignment_id": self.payload["assignment_id"],
            "payee_id": self.payload["payee_id"],
            # Deliberately omit the required idempotency_key.
        }

        response = self.create_payment(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
        self.assertEqual(response.data["error"], "Request validation failed.")
        self.assertIn("details", response.data)
        self.assertIn("idempotency_key", response.data["details"]["fields"])
        self.assertEqual(Payment.objects.count(), 0)

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

    def test_admin_can_view_another_users_payment(self):
        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=str(uuid4()),
            payee_id=str(uuid4()),
            amount="1500.00",
            fee="0.00",
            idempotency_key="admin-detail-test",
        )

        admin_id = str(uuid4())
        token = jwt.encode(
            {
                "user_id": admin_id,
                "role": "ADMIN",
                "iat": int(__import__("time").time()),
                "exp": int(__import__("time").time()) + 300,
                "token_type": "access",
            },
            os.getenv("JWT_SECRET_KEY"),
            algorithm="HS256",
        )

        admin_client = APIClient()
        admin_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        response = admin_client.get(
            f"/api/payments/{payment.id}/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["data"]["id"],
            str(payment.id),
        )


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

        self.assignment_patcher.stop()
        self.assignment_patcher = patch(
            "payments_notifications.views.get_assignment",
            return_value={
                "project_id": str(uuid4()),
                "student_id": str(payment.payee_id),
            },
        )
        self.assignment_patcher.start()
        self.addCleanup(self.assignment_patcher.stop)

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

        self.assignment_patcher.stop()
        self.assignment_patcher = patch(
            "payments_notifications.views.get_assignment",
            return_value={
                "project_id": str(uuid4()),
                "student_id": str(payment.payee_id),
            },
        )
        self.assignment_patcher.start()
        self.addCleanup(self.assignment_patcher.stop)

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

    def test_release_rejects_assignment_student_mismatch(self):
        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=self.user_id,
            payee_id=str(uuid4()),
            amount="1500.00",
            fee="0.00",
            status=Payment.Status.SUCCESS,
            idempotency_key="release-payee-mismatch-test",
        )

        self.assignment_patcher.stop()
        self.assignment_patcher = patch(
            "payments_notifications.views.get_assignment",
            return_value={
                "project_id": str(uuid4()),
                "student_id": str(uuid4()),
            },
        )
        self.assignment_patcher.start()
        self.addCleanup(self.assignment_patcher.stop)

        response = self.client.post(
            f"/api/payments/{payment.id}/release/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data["code"],
            "PAYEE_ASSIGNMENT_MISMATCH",
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)

    def test_release_rejects_project_owner_mismatch(self):
        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=self.user_id,
            payee_id=str(uuid4()),
            amount="1500.00",
            fee="0.00",
            status=Payment.Status.SUCCESS,
            idempotency_key="release-owner-mismatch-test",
        )

        self.assignment_patcher.stop()
        self.assignment_patcher = patch(
            "payments_notifications.views.get_assignment",
            return_value={
                "project_id": str(uuid4()),
                "student_id": str(payment.payee_id),
            },
        )
        self.assignment_patcher.start()
        self.addCleanup(self.assignment_patcher.stop)

        self.project_patcher.stop()
        self.project_patcher = patch(
            "payments_notifications.views.get_project",
            return_value={"client_id": str(uuid4())},
        )
        self.project_patcher.start()
        self.addCleanup(self.project_patcher.stop)

        response = self.client.post(
            f"/api/payments/{payment.id}/release/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["code"],
            "PAYER_PROJECT_MISMATCH",
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)

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

    def make_successful_payment(self):
        payment = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=self.user_id,
            payee_id=self.payload["payee_id"],
            amount="1500.00",
            fee="0.00",
            status=Payment.Status.SUCCESS,
            idempotency_key=f"release-{uuid4()}",
        )
        return payment

    def test_release_requires_submitted_work(self):
        payment = self.make_successful_payment()
        self.work_lookup.return_value = [{"status": "DRAFT"}]

        response = self.client.post(
            f"/api/payments/{payment.id}/release/", {}, format="json"
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "PAYMENT_RELEASE_NOT_ALLOWED")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)

    def test_release_notifies_payer_and_payee(self):
        payment = self.make_successful_payment()

        response = self.client.post(
            f"/api/payments/{payment.id}/release/", {}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        released = Notification.objects.filter(event="PAYMENT_RELEASED")
        self.assertEqual(
            {str(n.user_id) for n in released},
            {str(payment.payer_id), str(payment.payee_id)},
        )

        # Releasing again is idempotent and creates no new notifications.
        self.client.post(f"/api/payments/{payment.id}/release/", {}, format="json")
        self.assertEqual(released.count(), 2)

    def test_release_reports_work_service_outage(self):
        payment = self.make_successful_payment()
        self.work_lookup.side_effect = UpstreamServiceError(
            "down", "UPSTREAM_UNAVAILABLE", 503
        )

        response = self.client.post(
            f"/api/payments/{payment.id}/release/", {}, format="json"
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "UPSTREAM_UNAVAILABLE")

    def test_second_active_payment_for_assignment_conflicts(self):
        first = self.create_payment()
        self.assertEqual(first.status_code, 201)

        payload = dict(self.payload, idempotency_key="another-key")
        response = self.create_payment(payload)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "CONFLICT")
        self.assertEqual(
            response.data["details"]["payment_id"], first.data["data"]["id"]
        )

    def test_payment_response_identifies_mock_mode_and_fee(self):
        response = self.create_payment()
        data = response.data["data"]
        self.assertEqual(data["payment_mode"], "MOCK")
        self.assertEqual(data["fee"], "0.00")
        self.assertEqual(data["net_amount"], data["amount"])

    def test_payment_list_filters_by_assignment(self):
        self.create_payment()
        other = Payment.objects.create(
            assignment_id=uuid4(),
            payer_id=self.user_id,
            payee_id=uuid4(),
            amount="10.00",
            idempotency_key="other-assignment",
        )

        response = self.client.get(
            f"/api/payments/?assignment_id={self.payload['assignment_id']}"
        )

        self.assertEqual(response.status_code, 200)
        ids = [p["id"] for p in response.data["data"]]
        self.assertEqual(len(ids), 1)
        self.assertNotIn(str(other.id), ids)

        response = self.client.get("/api/payments/?assignment_id=nope")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")

    def test_empty_list_has_zero_total_pages(self):
        response = self.client.get("/api/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pagination"]["total"], 0)
        self.assertEqual(response.data["pagination"]["total_pages"], 0)

    @override_settings(MOCK_PAYMENT_ENABLED=False)
    def test_processing_without_provider_returns_503(self):
        payment_id = self.create_payment().data["data"]["id"]
        response = self.client.post(
            f"/api/payments/{payment_id}/process/", {}, format="json"
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "PAYMENT_PROVIDER_UNAVAILABLE")

    def test_errors_use_common_envelope(self):
        response = self.client.get(f"/api/payments/{uuid4()}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "NOT_FOUND")
        self.assertEqual(response.data["details"], {})

        anonymous = APIClient()
        response = anonymous.get("/api/payments/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "UNAUTHORIZED")

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
        self.assertEqual(response.data["code"], "VALIDATION_ERROR")
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
            "VALIDATION_ERROR",
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
