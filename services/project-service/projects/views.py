from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404

from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project
from .serializers import ProjectSerializer
from . import services


# ---------------------------------------------------------------- helpers

def get_client_id(user):
    """Return the client identifier supplied by the authentication layer."""
    client_id = getattr(user, "client_id", None) or getattr(user, "id", None)

    if client_id is None:
        raise PermissionDenied(
            "The authenticated user has no client identifier."
        )

    return client_id


def is_client(user):
    return str(getattr(user, "role", "")).lower() == "client"


def is_admin(user):
    return bool(
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or str(getattr(user, "role", "")).lower() == "admin"
    )


def is_owner(user, project):
    return is_client(user) and str(project.client_id) == str(
        get_client_id(user)
    )


def data_response(data, code=status.HTTP_200_OK):
    """Success envelope expected by the other services: {"data": ...}."""
    return Response({"data": data}, status=code)


def error_response(exc, code=status.HTTP_400_BAD_REQUEST):
    """Convert service and validation errors into API responses."""
    detail = getattr(exc, "messages", [str(exc)])
    return Response({"error": detail}, status=code)


def get_project_or_404(project_id):
    try:
        return Project.objects.get(pk=project_id)
    except (Project.DoesNotExist, ValueError):
        raise Http404("Project not found.")


def visible_projects(user):
    """Projects the given user is allowed to see."""
    if is_admin(user):
        return Project.objects.all()

    if is_client(user):
        return Project.objects.filter(
            Q(status=Project.Status.PUBLISHED)
            | Q(client_id=get_client_id(user))
        )

    return Project.objects.filter(status=Project.Status.PUBLISHED)


# ------------------------------------------------------------------ views

class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {"service": "project-service", "status": "healthy"},
            status=status.HTTP_200_OK,
        )


class ProjectListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            projects = services.search_projects(
                queryset=visible_projects(request.user),
                query=request.query_params.get("query"),
                skill=request.query_params.get("skill"),
                category=request.query_params.get("category"),
                max_budget=request.query_params.get("max_budget"),
            )
        except ValidationError as exc:
            return error_response(exc)

        return data_response(ProjectSerializer(projects, many=True).data)

    def post(self, request):
        if not is_client(request.user):
            return Response(
                {"error": "Only clients can create projects."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ProjectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = services.create_project(
                client_id=get_client_id(request.user),
                **serializer.validated_data,
            )
        except ValidationError as exc:
            return error_response(exc)

        return data_response(
            ProjectSerializer(project).data, status.HTTP_201_CREATED
        )


class ProjectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_project_or_404(project_id)

        if (
            project.status != Project.Status.PUBLISHED
            and not is_admin(request.user)
            and not is_owner(request.user, project)
        ):
            return Response(
                {"error": "You do not have permission to view this project."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return data_response(ProjectSerializer(project).data)

    def put(self, request, project_id):
        if not is_client(request.user):
            return Response(
                {"error": "Only clients can edit projects."},
                status=status.HTTP_403_FORBIDDEN,
            )

        project = get_project_or_404(project_id)
        serializer = ProjectSerializer(
            project, data=request.data, partial=True
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            updated = services.update_project(
                project=project,
                client_id=get_client_id(request.user),
                **serializer.validated_data,
            )
        except services.NotProjectOwner as exc:
            return error_response(exc, status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return error_response(exc)

        return data_response(ProjectSerializer(updated).data)

    def delete(self, request, project_id):
        project = get_project_or_404(project_id)

        if not (is_admin(request.user) or is_owner(request.user, project)):
            return Response(
                {
                    "error": "Only the owning client or an admin "
                    "can delete a project."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        project.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PublishProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        if not is_client(request.user):
            return Response(
                {"error": "Only clients can publish projects."},
                status=status.HTTP_403_FORBIDDEN,
            )

        project = get_project_or_404(project_id)

        try:
            project = services.publish_project(
                project=project, client_id=get_client_id(request.user)
            )
        except services.NotProjectOwner as exc:
            return error_response(exc, status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return error_response(exc)

        return data_response(ProjectSerializer(project).data)


class CloseProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        if not is_client(request.user):
            return Response(
                {"error": "Only clients can close projects."},
                status=status.HTTP_403_FORBIDDEN,
            )

        project = get_project_or_404(project_id)

        try:
            project = services.close_project(
                project=project, client_id=get_client_id(request.user)
            )
        except services.NotProjectOwner as exc:
            return error_response(exc, status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return error_response(exc)

        return data_response(ProjectSerializer(project).data)


class ProjectStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_project_or_404(project_id)

        if not (is_admin(request.user) or is_owner(request.user, project)):
            return Response(
                {"error": "You do not have permission to view this status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return data_response(
            {
                "id": str(project.id),
                "client_id": str(project.client_id),
                "title": project.title,
                "status": project.status,
                "budget": str(project.budget),
            }
        )
