
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project
from .serializers import ProjectSerializer
from . import services


def get_client_id(request):
    """Get the client ID from the authenticated user's identity."""
    user = request.user

    # Adapt this to the User Service's authentication integration.
    client_id = getattr(user, "client_id", None)

    if not client_id:
        client_id = getattr(user, "id", None)

    return str(client_id) if client_id else None


def is_client(request):
    """Check whether the authenticated user has the client role."""
    user = request.user
    role = getattr(user, "role", "")
    return str(role).lower() == "client"


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "service": "project-service",
            "status": "running",
        })


class ProjectListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        projects = services.search_projects(
            query=request.query_params.get("q"),
            skill=request.query_params.get("skill"),
            category=request.query_params.get("category"),
            max_budget=request.query_params.get("max_budget"),
        )

        if isinstance(projects, list):
            data = ProjectSerializer(projects, many=True).data
        else:
            data = ProjectSerializer(projects, many=True).data

        return Response(data)

    def post(self, request):
        if not is_client(request):
            return Response(
                {"detail": "Only clients can create projects."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_id = get_client_id(request)
        if not client_id:
            return Response(
                {"detail": "Client identity is unavailable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            project = services.create_project(
                client_id=client_id,
                **serializer.validated_data,
            )
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            ProjectSerializer(project).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, project_id):
        try:
            return Project.objects.get(pk=project_id)
        except (Project.DoesNotExist, ValueError):
            return None

    def get(self, request, project_id):
        project = self.get_object(project_id)
        if project is None:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if (
            project.status != Project.Status.PUBLISHED
            and str(project.client_id) != str(get_client_id(request))
            and not getattr(request.user, "is_staff", False)
        ):
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(ProjectSerializer(project).data)

    def put(self, request, project_id):
        project = self.get_object(project_id)
        if project is None:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not is_client(request):
            return Response(
                {"detail": "Only clients can edit projects."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ProjectSerializer(
            project,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        try:
            project = services.update_project(
                project=project,
                client_id=get_client_id(request),
                **serializer.validated_data,
            )
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ProjectSerializer(project).data)


class PublishProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        if not is_client(request):
            return Response(
                {"detail": "Only clients can publish projects."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            project = Project.objects.get(pk=project_id)
            project = services.publish_project(
                project=project,
                client_id=get_client_id(request),
            )
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValidationError, ValueError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ProjectSerializer(project).data)


class CloseProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        if not is_client(request):
            return Response(
                {"detail": "Only clients can close projects."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            project = Project.objects.get(pk=project_id)
            project = services.close_project(
                project=project,
                client_id=get_client_id(request),
            )
        except Project.DoesNotExist:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValidationError, ValueError) as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ProjectSerializer(project).data)


class ProjectStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        try:
            project = Project.objects.get(pk=project_id)
        except (Project.DoesNotExist, ValueError):
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if (
            str(project.client_id) != str(get_client_id(request))
            and not getattr(request.user, "is_staff", False)
        ):
            return Response(
                {"detail": "You cannot view this project's status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response({
            "id": str(project.id),
            "status": project.status,
        })
