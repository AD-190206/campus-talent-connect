import uuid

import jwt
from django.conf import settings
from rest_framework.authentication import (
    BaseAuthentication,
    get_authorization_header,
)
from rest_framework.exceptions import AuthenticationFailed

VALID_ROLES = {"STUDENT", "CLIENT", "ADMIN"}
REQUIRED_CLAIMS = ["exp", "iat", "user_id", "role", "token_type"]


class JWTUser:
    """User built from a verified access token (no database lookup)."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, user_id, role, payload):
        self.id = user_id
        self.pk = user_id
        self.role = role
        self.payload = payload

    def __str__(self):
        return str(self.id)


class JWTAuthentication(BaseAuthentication):
    """Validates the shared JWT contract (HS256, access tokens only)."""

    def authenticate(self, request):
        header = get_authorization_header(request).split()

        if not header or header[0].lower() != b"bearer":
            return None

        if len(header) != 2:
            raise AuthenticationFailed("Invalid Authorization header.")

        try:
            token = header[1].decode("ascii")
        except UnicodeError:
            raise AuthenticationFailed("Invalid token.")

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=["HS256"],
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token.")

        if payload.get("token_type") != "access":
            raise AuthenticationFailed("An access token is required.")

        role = payload.get("role")
        if not isinstance(role, str) or role not in VALID_ROLES:
            raise AuthenticationFailed("Invalid role claim.")

        user_id = payload.get("user_id")
        try:
            parsed = uuid.UUID(user_id)
        except (TypeError, ValueError, AttributeError):
            raise AuthenticationFailed("Invalid user_id claim.")

        if str(parsed) != user_id.lower():
            raise AuthenticationFailed("Invalid user_id claim.")

        return (JWTUser(parsed, role, payload), token)

    def authenticate_header(self, request):
        return "Bearer"
