import uuid
from rest_framework.permissions import IsAuthenticated
from .authentication import JWTAuthentication
from datetime import datetime, timedelta, timezone
import os

import jwt
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import transaction

from .models import User, StudentProfile, ClientProfile, RefreshToken
from .serializers import RegisterSerializer, UserUpdateSerializer


def generate_access_token(user):
    secret = os.getenv("JWT_SECRET_KEY")

    if not secret or len(secret.encode("utf-8")) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured with at least 32 bytes."
        )

    now = datetime.now(timezone.utc)

    payload = {
        "user_id": str(user.public_id),
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "token_type": "access",
        "jti": str(uuid.uuid4()),
    }

    return jwt.encode(
        payload,
        secret,
        algorithm="HS256",
    )

def generate_refresh_token(user):
    secret = os.getenv("JWT_SECRET_KEY")

    if not secret or len(secret.encode("utf-8")) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured with at least 32 bytes."
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)

    payload = {
        "user_id": str(user.public_id),
        "role": user.role,
        "iat": now,
        "exp": expires_at,
        "token_type": "refresh",
        "jti": str(uuid.uuid4()),
    }

    token = jwt.encode(payload, secret, algorithm="HS256")

    RefreshToken.objects.create(
        user=user,
        token_hash=RefreshToken.hash_token(token),
        expires_at=expires_at,
    )

    return token


class HealthView(APIView):
    def get(self, request):
        return Response({
            "data": {
                "service": "user-service",
                "status": "healthy",
            },
            "message": "Health check successful.",
        })

class RegisterView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
    {
        "data": {
            "user_id": str(user.public_id),
            "email": user.email,
            "role": user.role,
        },
        "message": "Registration successful.",
    },
    status=status.HTTP_201_CREATED,
)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = request.data.get("email", "")
        password = request.data.get("password", "")

        if not isinstance(email, str) or not isinstance(password, str):
                        return Response(
                {
                    "error": "Email and password must be strings.",
                    "code": "VALIDATION_ERROR",
                    "details": {
                        "fields": {
                            "email": "Must be a string.",
                            "password": "Must be a string.",
                        }
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(
            request,
            username=email.strip().lower(),
            password=password,
        )
        if user is None or not user.is_active:
            return Response(
                {
                    "error": "Invalid email or password.",
                    "code": "UNAUTHORIZED",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )


        access_token = generate_access_token(user)
        refresh_token = generate_refresh_token(user)

        return Response(
    {
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 1800,
            "user": {
                "user_id": str(user.public_id),
                "email": user.email,
                "role": user.role,
            },
        },
        "message": "Login successful.",
    },
    status=status.HTTP_200_OK,
)


class CurrentUserView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response(
    {
        "data": {
            "user_id": str(user.public_id),
            "email": user.email,
            "role": user.role,
        },
        "message": "Current user retrieved successfully.",
    },
    status=status.HTTP_200_OK,
)



class RefreshTokenView(APIView):
    authentication_classes = []
    permission_classes = []

    @transaction.atomic
    def post(self, request):
        refresh_token = request.data.get("refresh_token")

        if not isinstance(refresh_token, str) or not refresh_token:
            return Response(
                {
                    "error": "Refresh token is required.",
                    "code": "REFRESH_TOKEN_REQUIRED",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        secret = os.getenv("JWT_SECRET_KEY")

        if not secret or len(secret.encode("utf-8")) < 32:
            return Response(
                {
                    "error": "Authentication service is not configured.",
                    "code": "AUTH_CONFIGURATION_ERROR",
                    "details": {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            payload = jwt.decode(
                refresh_token,
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
        except jwt.InvalidTokenError:
            return Response(
                {
                    "error": "Invalid or expired refresh token.",
                    "code": "INVALID_REFRESH_TOKEN",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if payload.get("token_type") != "refresh":
            return Response(
                {
                    "error": "A refresh token is required.",
                    "code": "INVALID_REFRESH_TOKEN",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token_hash = RefreshToken.hash_token(refresh_token)

        try:
            stored_token = RefreshToken.objects.select_for_update().get(
                token_hash=token_hash
            )
        except RefreshToken.DoesNotExist:
            return Response(
                {
                    "error": "Refresh token is invalid or already revoked.",
                    "code": "INVALID_REFRESH_TOKEN",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if (
            not stored_token.is_valid
            or str(stored_token.user.public_id) != payload["user_id"]
            or stored_token.user.role != payload["role"]
        ):
            return Response(
                {
                    "error": "Refresh token is invalid or already revoked.",
                    "code": "INVALID_REFRESH_TOKEN",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = stored_token.user
        stored_token.revoked_at = datetime.now(timezone.utc)
        stored_token.save(update_fields=["revoked_at"])

        new_access_token = generate_access_token(user)
        new_refresh_token = generate_refresh_token(user)

        return Response(
            {
                "data": {
                    "access_token": new_access_token,
                    "refresh_token": new_refresh_token,
                    "token_type": "Bearer",
                    "expires_in": 1800,
                },
                "message": "Tokens refreshed successfully.",
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        refresh_token = request.data.get("refresh_token")

        if not isinstance(refresh_token, str) or not refresh_token:
            return Response(
                {
                    "error": "Refresh token is required.",
                    "code": "REFRESH_TOKEN_REQUIRED",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        secret = os.getenv("JWT_SECRET_KEY")

        if not secret or len(secret.encode("utf-8")) < 32:
            return Response(
                {
                    "error": "Authentication service is not configured.",
                    "code": "AUTH_CONFIGURATION_ERROR",
                    "details": {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            payload = jwt.decode(
                refresh_token,
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
        except jwt.InvalidTokenError:
            return Response(
                {
                    "error": "Invalid or expired refresh token.",
                    "code": "INVALID_REFRESH_TOKEN",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if payload.get("token_type") != "refresh":
            return Response(
                {
                    "error": "A refresh token is required.",
                    "code": "INVALID_REFRESH_TOKEN",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token_hash = RefreshToken.hash_token(refresh_token)
        now = datetime.now(timezone.utc)

        updated = RefreshToken.objects.filter(
            token_hash=token_hash,
            revoked_at__isnull=True,
            user__is_active=True,
            user__role=payload["role"],
            user__public_id=payload["user_id"],
            expires_at__gt=now,
        ).update(revoked_at=now)

        if not updated:
            return Response(
                {
                    "error": "Invalid or already revoked refresh token.",
                    "code": "INVALID_REFRESH_TOKEN",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "data": {},
                "message": "Logged out successfully.",
            },
            status=status.HTTP_200_OK,
        )


class UserDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if str(request.user.public_id) != str(user_id) and request.user.role != "ADMIN":
            return Response(
                {
                    "error": "You can only view your own account.",
                    "code": "FORBIDDEN",
                    "details": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = request.user if str(request.user.public_id) == str(user_id) else None

        if user is None:
            try:
                user = User.objects.get(public_id=user_id)
            except (User.DoesNotExist, ValueError, TypeError):
                return Response(
                    {
                        "error": "User not found.",
                        "code": "NOT_FOUND",
                        "details": {},
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            {
                "data": {
                    "user_id": str(user.public_id),
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                },
                "message": "User details retrieved successfully.",
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, user_id):
        if str(request.user.public_id) != str(user_id) and request.user.role != "ADMIN":
            return Response(
                {
                    "error": "You can only update your own account.",
                    "code": "FORBIDDEN",
                    "details": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            user = User.objects.get(public_id=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response(
                {
                    "error": "User not found.",
                    "code": "NOT_FOUND",
                    "details": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UserUpdateSerializer(
            user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "data": {
                    "user_id": str(user.public_id),
                    "email": user.email,
                    "role": user.role,
                },
                "message": "Account updated successfully.",
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, user_id):
        return self.put(request, user_id)



class UserProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_profile(self, user):
        if user.role == "STUDENT":
            try:
                profile = user.student_profile
            except StudentProfile.DoesNotExist:
                return None

            return {
                "name": profile.name,
                "phone": profile.phone,
                "college": profile.college,
                "skills": profile.skills,
                "portfolio_url": profile.portfolio_url,
                "rating": profile.rating,
            }

        if user.role == "CLIENT":
            try:
                profile = user.client_profile
            except ClientProfile.DoesNotExist:
                return None

            return {
                "company_name": profile.company_name,
                "contact_person": profile.contact_person,
                "phone": profile.phone,
            }

        return None

    def get_target_user(self, request, user_id):
        if str(request.user.public_id) == str(user_id):
            return request.user

        if request.user.role != "ADMIN":
            return None

        try:
            return User.objects.get(public_id=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return False

    def get(self, request, user_id):
        user = self.get_target_user(request, user_id)

        if user is None:
            return Response(
                {
                    "error": "You can only view your own profile.",
                    "code": "FORBIDDEN",
                    "details": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user is False:
            return Response(
                {
                    "error": "User not found.",
                    "code": "NOT_FOUND",
                    "details": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        profile_data = self.get_profile(user)

        if profile_data is None:
            return Response(
                {
                    "error": "Profile not found.",
                    "code": "NOT_FOUND",
                    "details": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "data": profile_data,
                "message": "Profile retrieved successfully.",
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request, user_id):
        user = self.get_target_user(request, user_id)

        if user is None:
            return Response(
                {
                    "error": "You can only update your own profile.",
                    "code": "FORBIDDEN",
                    "details": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user is False:
            return Response(
                {
                    "error": "User not found.",
                    "code": "NOT_FOUND",
                    "details": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.role == "STUDENT":
            try:
                profile = user.student_profile
            except StudentProfile.DoesNotExist:
                return Response(
                    {
                        "error": "Profile not found.",
                        "code": "NOT_FOUND",
                        "details": {},
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            allowed_fields = {
                "name", "phone", "college", "skills", "portfolio_url"
            }

        elif user.role == "CLIENT":
            try:
                profile = user.client_profile
            except ClientProfile.DoesNotExist:
                return Response(
                    {
                        "error": "Profile not found.",
                        "code": "NOT_FOUND",
                        "details": {},
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            allowed_fields = {"company_name", "contact_person", "phone"}

        else:
            return Response(
                {
                    "error": "This user role does not have an editable profile.",
                    "code": "VALIDATION_ERROR",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        unexpected_fields = set(request.data.keys()) - allowed_fields

        if unexpected_fields:
            return Response(
                {
                    "error": "Unsupported profile fields.",
                    "code": "VALIDATION_ERROR",
                    "details": {
                        "fields": {
                            field: "This field is not allowed."
                            for field in sorted(unexpected_fields)
                        }
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        for field in allowed_fields.intersection(request.data.keys()):
            value = request.data[field]

            if not isinstance(value, str):
                return Response(
                    {
                        "error": f"{field} must be a string.",
                        "code": "VALIDATION_ERROR",
                        "details": {
                            "fields": {
                                field: "Must be a string."
                            }
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if field in {"name", "contact_person"} and not value.strip():
                return Response(
                    {
                        "error": f"{field} cannot be blank.",
                        "code": "VALIDATION_ERROR",
                        "details": {
                            "fields": {
                                field: "This field cannot be blank."
                            }
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            setattr(profile, field, value)

        profile.save()

        return Response(
            {
                "data": self.get_profile(user),
                "message": "Profile updated successfully.",
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, user_id):
        return self.put(request, user_id)



class DeactivateUserView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        is_owner = str(request.user.public_id) == str(user_id)
        is_admin = request.user.role == "ADMIN"

        if not is_owner and not is_admin:
            return Response(
                {
                    "error": "You can only deactivate your own account.",
                    "code": "FORBIDDEN",
                    "details": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if is_owner and not request.user.is_active:
            return Response(
                {
                    "error": "This account is already deactivated.",
                    "code": "CONFLICT",
                    "details": {},
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            user = User.objects.get(public_id=user_id)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response(
                {
                    "error": "User not found.",
                    "code": "NOT_FOUND",
                    "details": {},
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not user.is_active:
            return Response(
                {
                    "error": "This account is already deactivated.",
                    "code": "CONFLICT",
                    "details": {},
                },
                status=status.HTTP_409_CONFLICT,
            )

        user.is_active = False
        user.save(update_fields=["is_active"])

        return Response(
            {
                "data": {
                    "user_id": str(user.public_id),
                    "is_active": user.is_active,
                },
                "message": "Account deactivated successfully.",
            },
            status=status.HTTP_200_OK,
            )
