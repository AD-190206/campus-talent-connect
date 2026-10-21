from rest_framework.permissions import IsAuthenticated
from .authentication import JWTAuthentication
from datetime import datetime, timedelta, timezone
import os

import jwt
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User, StudentProfile, ClientProfile
from .serializers import RegisterSerializer, UserUpdateSerializer


def generate_access_token(user):
    now = datetime.now(timezone.utc)

    payload = {
        "user_id": str(user.pk),
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }

    return jwt.encode(
        payload,
        os.getenv("JWT_SECRET_KEY", "development-only-jwt-secret"),
        algorithm="HS256",
    )


class HealthView(APIView):
    def get(self, request):
        return Response({
            "service": "user-service",
            "status": "running",
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
                "message": "Registration successful",
                "user": {
                    "user_id": str(user.pk),
                    "email": user.email,
                    "role": user.role,
                },
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
                {"error": "Email and password must be strings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(
            request,
            username=email.strip().lower(),
            password=password,
        )

        if user is None or not user.is_active:
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        access_token = generate_access_token(user)

        return Response({
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 1800,
            "user": {
                "user_id": str(user.pk),
                "email": user.email,
                "role": user.role,
            },
        })


class CurrentUserView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response({
            "user_id": str(user.pk),
            "email": user.email,
            "role": user.role,
        })


class RefreshTokenView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        new_token = generate_access_token(request.user)

        return Response({
            "access_token": new_token,
            "token_type": "Bearer",
            "expires_in": 1800,
        })


class UserDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        if str(request.user.pk) != str(user_id):
            return Response(
                {"error": "You can only view your own account."},
                status=status.HTTP_403_FORBIDDEN,
            )
    def put(self, request, user_id):
        if str(request.user.pk) != str(user_id):
            return Response(
                {"error": "You can only update your own account."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = UserUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response({
            "message": "Account updated successfully",
            "user_id": str(user.pk),
            "email": user.email,
            "role": user.role,
        })

        user = request.user

        return Response({
            "user_id": str(user.pk),
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        })

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

    def get(self, request, user_id):
        if str(request.user.pk) != str(user_id):
            return Response(
                {"error": "You can only view your own profile."},
                status=status.HTTP_403_FORBIDDEN,
            )

        profile_data = self.get_profile(request.user)

        if profile_data is None:
            return Response(
                {"error": "Profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(profile_data)

    def put(self, request, user_id):
        if str(request.user.pk) != str(user_id):
            return Response(
                {"error": "You can only update your own profile."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user = request.user

        if user.role == "STUDENT":
            try:
                profile = user.student_profile
            except StudentProfile.DoesNotExist:
                return Response(
                    {"error": "Profile not found."},
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
                    {"error": "Profile not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            allowed_fields = {"company_name", "contact_person", "phone"}

        else:
            return Response(
                {"error": "Unsupported user role."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        unexpected_fields = set(request.data.keys()) - allowed_fields

        if unexpected_fields:
            return Response(
                {
                    "error": "Unsupported profile fields.",
                    "fields": sorted(unexpected_fields),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        for field in allowed_fields.intersection(request.data.keys()):
            value = request.data[field]

            if not isinstance(value, str):
                return Response(
                    {"error": f"{field} must be a string."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if field in {"name", "contact_person"} and not value.strip():
                return Response(
                    {"error": f"{field} cannot be blank."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            setattr(profile, field, value)

        profile.save()

        return Response({
            "message": "Profile updated successfully",
            "profile": self.get_profile(user),
        })

class DeactivateUserView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if str(request.user.pk) != str(user_id):
            return Response(
                {"error": "You can only deactivate your own account."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user = request.user
        user.is_active = False
        user.save(update_fields=["is_active"])

        return Response(
            {"message": "Account deactivated successfully."},
            status=status.HTTP_200_OK,
        )
