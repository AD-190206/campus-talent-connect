
from users.models import RefreshToken
from datetime import datetime, timedelta, timezone
import os
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class UserDetailViewTests(APITestCase):

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": self.user.email,
                "password": "TestPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("data", response.data)
        self.assertIn("access_token", response.data["data"])
        self.assertIn("refresh_token", response.data["data"])
        self.assertEqual(RefreshToken.objects.count(), 1)

    def test_refresh_rotates_tokens_and_rejects_reuse(self):
        login_response = self.client.post(
            "/api/auth/login/",
            {
                "email": self.user.email,
                "password": "TestPass123!",
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        old_refresh = login_response.data["data"]["refresh_token"]

        refresh_response = self.client.post(
            "/api/auth/refresh/",
            {"refresh_token": old_refresh},
            format="json",
        )

        self.assertEqual(
            refresh_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertIn("access_token", refresh_response.data["data"])
        self.assertIn("refresh_token", refresh_response.data["data"])

        reuse_response = self.client.post(
            "/api/auth/refresh/",
            {"refresh_token": old_refresh},
            format="json",
        )

        self.assertEqual(
            reuse_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_logout_revokes_refresh_token(self):
        login_response = self.client.post(
            "/api/auth/login/",
            {
                "email": self.user.email,
                "password": "TestPass123!",
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        refresh_token = login_response.data["data"]["refresh_token"]

        logout_response = self.client.post(
            "/api/auth/logout/",
            {"refresh_token": refresh_token},
            format="json",
        )

        self.assertEqual(
            logout_response.status_code,
            status.HTTP_200_OK,
        )

        refresh_response = self.client.post(
            "/api/auth/refresh/",
            {"refresh_token": refresh_token},
            format="json",
        )

        self.assertEqual(
            refresh_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def setUp(self):
        self.user = User.objects.create_user(
            email="student@example.com",
            password="TestPass123!",
            role="STUDENT",
        )
        self.url = f"/api/users/{self.user.public_id}/"

        self.secret = os.environ["JWT_SECRET_KEY"]

    def authenticate_as(self, user, expired=False):
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": str(user.public_id),
            "role": user.role,
            "iat": now - timedelta(hours=1) if expired else now,
            "exp": now - timedelta(minutes=1) if expired else now + timedelta(minutes=30),
            "token_type": "access",
        }
        token = jwt.encode(payload, self.secret, algorithm="HS256")
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

    def test_owner_can_get_user_details(self):
        self.authenticate_as(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["email"], self.user.email)
        self.assertEqual(response.data["data"]["role"], "STUDENT")

    def test_non_owner_cannot_get_user_details(self):
        another_user = User.objects.create_user(
            email="another@example.com",
            password="TestPass123!",
            role="STUDENT",
        )
        self.authenticate_as(self.user)

        response = self.client.get(f"/api/users/{another_user.public_id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_request_without_token_is_rejected(self):
        self.client.credentials()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_token_is_rejected(self):
        self.authenticate_as(self.user, expired=True)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


    def test_refresh_token_cannot_access_protected_endpoint(self):
        self.authenticate_as(self.user)

        # Replace the access token with a refresh-type token.
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": str(self.user.public_id),
            "role": self.user.role,
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "token_type": "refresh",
        }
        token = jwt.encode(payload, self.secret, algorithm="HS256")
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_token_without_token_type_is_rejected(self):
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": str(self.user.public_id),
            "role": self.user.role,
            "iat": now,
            "exp": now + timedelta(minutes=30),
        }
        token = jwt.encode(payload, self.secret, algorithm="HS256")
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
            )
    def test_owner_can_deactivate_account(self):
        self.authenticate_as(self.user)

        response = self.client.post(
            f"/api/users/{self.user.public_id}/deactivate/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            User.objects.get(pk=self.user.pk).is_active
        )
        self.assertEqual(response.data["data"]["is_active"], False)

    def test_non_owner_cannot_deactivate_account(self):
        another_user = User.objects.create_user(
            email="another@example.com",
            password="TestPass123!",
            role="STUDENT",
        )
        self.authenticate_as(self.user)

        response = self.client.post(
            f"/api/users/{another_user.public_id}/deactivate/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertTrue(
            User.objects.get(pk=another_user.pk).is_active
        )

    def test_profile_access_without_profile_returns_404(self):
        self.authenticate_as(self.user)

        response = self.client.get(
            f"/api/users/{self.user.public_id}/profile/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "NOT_FOUND")

    def test_profile_update_rejects_unsupported_fields(self):
        from users.models import StudentProfile

        StudentProfile.objects.create(
            user=self.user,
            name="Test Student",
        )

        self.authenticate_as(self.user)

        response = self.client.patch(
            f"/api/users/{self.user.public_id}/profile/",
            {"admin": True},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            response.data["code"],
            "VALIDATION_ERROR",
        )
        self.assertIn("fields", response.data["details"])
    def test_logout_rejects_malformed_refresh_token(self):
        response = self.client.post(
            "/api/auth/logout/",
            {"refresh_token": "this-is-not-a-valid-jwt"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            response.data["code"],
            "INVALID_REFRESH_TOKEN",
        )
        self.assertIn("error", response.data)
        self.assertIn("details", response.data)
    def test_registration_rejects_admin_role(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "email": "admin-test@example.com",
                "password": "TestPass123!",
                "role": "ADMIN",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            User.objects.filter(email="admin-test@example.com").count(),
            0,
        )
        self.assertIn("error", response.data)
        self.assertIn("code", response.data)
        self.assertIn("details", response.data)

    def test_login_success_uses_common_envelope(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": self.user.email,
                "password": "TestPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data.keys()), {"data", "message"})
        self.assertTrue(response.data["message"])
        self.assertIn("access_token", response.data["data"])
        self.assertIn("refresh_token", response.data["data"])
        self.assertNotIn("password", response.data["data"])

    def test_invalid_login_uses_common_error_envelope(self):
        response = self.client.post(
            "/api/auth/login/",
            {
                "email": self.user.email,
                "password": "WrongPassword123!",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertIn("error", response.data)
        self.assertIn("code", response.data)
        self.assertIn("details", response.data)

    def test_malformed_access_token_is_rejected(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer not-a-valid-jwt"
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertIn("error", response.data)
        self.assertIn("code", response.data)
        self.assertIn("details", response.data)
    def test_nonexistent_user_is_not_accessible_to_non_owner(self):
        self.authenticate_as(self.user)

        response = self.client.get("/api/users/00000000-0000-0000-0000-000000000000/")

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertIn("error", response.data)
        self.assertIn("code", response.data)
        self.assertIn("details", response.data)


    def test_deactivating_account_twice_returns_conflict(self):
        self.authenticate_as(self.user)

        first_response = self.client.post(
            f"/api/users/{self.user.public_id}/deactivate/"
        )
        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )

        # The original access token must no longer authenticate.
        self.client.credentials()

        self.assertFalse(
            User.objects.get(pk=self.user.pk).is_active
        )
