import os
import jwt

from rest_framework.test import APIClient
from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Payment, Notification


class PaymentNotificationAPITests(TestCase):
    def setUp(self):
        self.client = self.authenticated_client()
        self.payload = {
            "assignment_id": str(uuid4()),
            "payer_id": str(uuid4()),
            "payee_id": str(uuid4()),
            "amount": "1500.00",
            "idempotency_key": "test-payment-key-001",
        }

    def create_payment(self, payload=None):
        return self.client.post(
            "/api/payments/",
            payload or self.payload,
            format="json",
        )

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
            "user_id": str(uuid4()),
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

    def authenticated_client(self):
        secret = os.getenv("JWT_SECRET_KEY")

        token = jwt.encode(
            {"user_id": str(uuid4())},
            secret,
            algorithm="HS256",
        )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client
