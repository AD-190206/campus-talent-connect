from django.urls import path

from .views import (
    ApplicationDetailView,
    ApplicationListCreateView,
    ApplicationRejectView,
    ApplicationSelectView,
    ApplicationShortlistView,
    ApplicationWithdrawView,
    AssignmentCompleteView,
    AssignmentDetailView,
    AssignmentListView,
    HealthView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),

    # Applications
    path("applications/", ApplicationListCreateView.as_view(), name="application-list-create"),
    path("applications/<uuid:pk>/", ApplicationDetailView.as_view(), name="application-detail"),

    # Status transitions
    path("applications/<uuid:pk>/shortlist/", ApplicationShortlistView.as_view(), name="application-shortlist"),
    path("applications/<uuid:pk>/select/", ApplicationSelectView.as_view(), name="application-select"),
    path("applications/<uuid:pk>/reject/", ApplicationRejectView.as_view(), name="application-reject"),
    path("applications/<uuid:pk>/withdraw/", ApplicationWithdrawView.as_view(), name="application-withdraw"),

    # Assignments
    path("assignments/", AssignmentListView.as_view(), name="assignment-list"),
    path("assignments/<uuid:pk>/", AssignmentDetailView.as_view(), name="assignment-detail"),
    path("assignments/<uuid:pk>/complete/", AssignmentCompleteView.as_view(), name="assignment-complete"),
]
