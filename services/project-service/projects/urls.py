
from django.urls import path

from .views import (
    HealthView,
    ProjectListCreateView,
    ProjectDetailView,
    PublishProjectView,
    StartProjectView,
    CompleteProjectView,
    CloseProjectView,
    ProjectStatusView,
)


urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path(
        "projects/",
        ProjectListCreateView.as_view(),
        name="project-list-create",
    ),
    path(
        "projects/<uuid:project_id>/",
        ProjectDetailView.as_view(),
        name="project-detail",
    ),
    path(
        "projects/<uuid:project_id>/publish/",
        PublishProjectView.as_view(),
        name="project-publish",
    ),
    path(
        "projects/<uuid:project_id>/start/",
        StartProjectView.as_view(),
        name="project-start",
    ),
    path(
        "projects/<uuid:project_id>/complete/",
        CompleteProjectView.as_view(),
        name="project-complete",
    ),
    path(
        "projects/<uuid:project_id>/close/",
        CloseProjectView.as_view(),
        name="project-close",
    ),
    path(
        "projects/<uuid:project_id>/status/",
        ProjectStatusView.as_view(),
        name="project-status",
    ),
]
