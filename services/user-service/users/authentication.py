
import os

import jwt
from django.contrib.auth import get_user_model
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

User = get_user_model()


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()

        if not header:
            return None

        if header[0].lower() != b"bearer":
            return None

        if len(header) != 2:
            raise exceptions.AuthenticationFailed(
                "Invalid Authorization header."
            )

        secret = os.getenv(
            "JWT_SECRET_KEY",
            "development-only-jwt-secret",
        )

        try:
            payload = jwt.decode(
                header[1],
                secret,
                algorithms=["HS256"],
                options={"require": ["user_id", "role", "exp"]},
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token.")

        user_id = payload.get("user_id")
        role = payload.get("role")

        try:
            user = User.objects.get(pk=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            raise exceptions.AuthenticationFailed("User not found.")

        if not user.is_active:
            raise exceptions.AuthenticationFailed("User account is inactive.")

        if user.role != role:
            raise exceptions.AuthenticationFailed("Invalid token claims.")

        return (user, payload)

    def authenticate_header(self, request):
        return "Bearer"
