
import os

import jwt
from uuid import UUID
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header


class JWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        # No token: let the permission class decide whether authentication
        # is required for this endpoint.
        if not auth:
            return None

        if auth[0].lower() != b"bearer":
            return None

        if len(auth) != 2:
            raise exceptions.AuthenticationFailed(
                "Invalid Authorization header."
            )

        token = auth[1].decode("utf-8")
        secret = os.getenv("JWT_SECRET_KEY")

        if not secret:
            raise exceptions.AuthenticationFailed(
                "JWT authentication is not configured."
            )

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={
                    "require": [
                        "user_id",
                        "role",
                        "iat",
                        "exp",
                        "token_type",
                    ],
                },
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed("Invalid token.")

        user_id = payload["user_id"]
        role = payload["role"]

        if not isinstance(user_id, str) or not user_id.strip():
            raise exceptions.AuthenticationFailed(
                "Token must contain a valid user identifier."
            )

        try:
            UUID(user_id)
        except (ValueError, AttributeError):
            raise exceptions.AuthenticationFailed(
                "Token must contain a valid UUID user identifier."
            )

        if role not in {"STUDENT", "CLIENT", "ADMIN"}:
            raise exceptions.AuthenticationFailed(
                "Token contains an invalid role."
            )

        if payload["token_type"] != "access":
            raise exceptions.AuthenticationFailed(
                "An access token is required."
            )

        # This service does not own the user database. Use the verified
        # JWT claims rather than querying a local Django User model.
        return (JWTUser(user_id, payload), token)


class JWTUser:
    def __init__(self, user_id, payload):
        self.id = str(user_id)
        self.pk = self.id
        self.payload = payload
        self.role = payload["role"]
        self.is_authenticated = True
        self.is_anonymous = False

    def __str__(self):
        return self.id
