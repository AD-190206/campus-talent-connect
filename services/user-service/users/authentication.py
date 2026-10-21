
import os

import jwt
from django.contrib.auth import get_user_model
from rest_framework import exceptions
from rest_framework.authentication import (
    BaseAuthentication,
    get_authorization_header,
)

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

        secret = os.getenv("JWT_SECRET_KEY")

        if not secret or len(secret.encode("utf-8")) < 32:
            raise exceptions.AuthenticationFailed(
                "JWT secret is not configured correctly."
            )

        try:
            payload = jwt.decode(
                header[1],
                secret,
                algorithms=["HS256"],
                options={
                    "require": [
                        "user_id",
                        "role",
                        "iat",
                        "exp",
                        "token_type",
                    ]
                },
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token.")

        # Protected endpoints accept access tokens only.
        if payload.get("token_type") != "access":
            raise exceptions.AuthenticationFailed(
                "Access token required."
            )

        user_id = payload.get("user_id")
        role = payload.get("role")

        if not isinstance(user_id, str) or not user_id:
            raise exceptions.AuthenticationFailed("Invalid token claims.")

        if not isinstance(role, str) or not role:
            raise exceptions.AuthenticationFailed("Invalid token claims.")

        try:
            user = User.objects.get(public_id=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            raise exceptions.AuthenticationFailed("User not found.")

        if not user.is_active:
            raise exceptions.AuthenticationFailed(
                "User account is inactive."
            )

        if user.role != role:
            raise exceptions.AuthenticationFailed("Invalid token claims.")

        return (user, payload)

    def authenticate_header(self, request):
        return "Bearer"
