import os
import uuid

import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


ALLOWED_ROLES = {"STUDENT", "CLIENT", "ADMIN"}


class JWTUser:
    def __init__(self, user_id, role):
        self.id = user_id
        self.user_id = user_id
        self.role = role
        self.is_authenticated = True


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")

        if not header:
            return None

        parts = header.split()

        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationFailed("Invalid Authorization header.")

        token = parts[1]
        secret = os.getenv("JWT_SECRET_KEY")

        if not secret:
            raise AuthenticationFailed(
                "JWT authentication is not configured."
            )

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={
                    "require": ["user_id", "role", "iat", "exp", "token_type"],
                },
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token.")

        if payload.get("token_type") != "access":
            raise AuthenticationFailed(
                "An access token is required."
            )

        user_id = payload.get("user_id")
        role = payload.get("role")

        if not isinstance(user_id, str):
            raise AuthenticationFailed(
                "Token user_id must be a UUID string."
            )

        try:
            parsed_user_id = uuid.UUID(user_id)
        except (ValueError, TypeError, AttributeError):
            raise AuthenticationFailed(
                "Token user_id must be a valid UUID."
            )

        # Require the canonical UUID string representation.
        if str(parsed_user_id) != user_id:
            raise AuthenticationFailed(
                "Token user_id must use canonical UUID format."
            )

        if role not in ALLOWED_ROLES:
            raise AuthenticationFailed(
                "Token does not contain a valid role."
            )

        return JWTUser(user_id, role), token

    def authenticate_header(self, request):
        return "Bearer"
