
import os

import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


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
            raise AuthenticationFailed("JWT authentication is not configured.")

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token.")

        user_id = payload.get("user_id")
        role = payload.get("role")

        if not user_id or role not in {"STUDENT", "CLIENT", "ADMIN"}:
            raise AuthenticationFailed("Token does not contain a valid user identity.")

        return JWTUser(user_id, role), token
