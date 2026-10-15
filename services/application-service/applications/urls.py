from django.urls import path
from .views import (
    HealthView,
    ApplicationListCreateView,
    ApplicationDetailView,
    ApplicationShortlistView,
    ApplicationSelectView,
    ApplicationRejectView,
    ApplicationWithdrawView,
    AssignmentListView,
    AssignmentDetailView,
)

urlpatterns = [
    # Health check
    path("health/", HealthView.as_view(), name="health"),

    # Applications
    path("applications/",          ApplicationListCreateView.as_view(), name="application-list-create"),
    path("applications/<int:pk>/", ApplicationDetailView.as_view(),     name="application-detail"),

    # Status transitions
    path("applications/<int:pk>/shortlist/", ApplicationShortlistView.as_view(), name="application-shortlist"),
    path("applications/<int:pk>/select/",    ApplicationSelectView.as_view(),    name="application-select"),
    path("applications/<int:pk>/reject/",    ApplicationRejectView.as_view(),    name="application-reject"),
    path("applications/<int:pk>/withdraw/",  ApplicationWithdrawView.as_view(),  name="application-withdraw"),

    # Assignments
    path("assignments/",          AssignmentListView.as_view(),   name="assignment-list"),
    path("assignments/<int:pk>/", AssignmentDetailView.as_view(), name="assignment-detail"),
]