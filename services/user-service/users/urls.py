
from django.urls import path

from .views import (
    UserProfileView,
    HealthView,
    RegisterView,
    LoginView,
    CurrentUserView,
    RefreshTokenView,
    UserDetailView,
    DeactivateUserView,
    LogoutView,
)


urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("auth/refresh/", RefreshTokenView.as_view(), name="refresh-token"),
    path("users/<str:user_id>/", UserDetailView.as_view(), name="user-detail"),
    path(
    "users/<str:user_id>/profile/",
    UserProfileView.as_view(),
    name="user-profile",
),
path(
    "users/<str:user_id>/deactivate/",
    DeactivateUserView.as_view(),
    name="deactivate-user",
),
path("auth/logout/", LogoutView.as_view(), name="logout"),
]
