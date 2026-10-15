
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project
from .serializers import ProjectSerializer
from . import services


def get_client_id(request):
    """Get the client ID from the authenticated user's identity."""
    user = request.user

    client_id = getattr(user, "client_id", None)

    if not client_id:
        client_id = getattr(user, "id", None)

    return str(client_id) if client_id else None


def is_client(request):
    """Check whether the authenticated user has the client role."""
    role = getattr(request.user, "role", "")
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
        max_budget = request.query_params.get("max_budget")

        if max_budget is not None:
            try:
                from decimal import Decimal, InvalidOperation

                max_budget = Decimal(max_budget)

                if not max_budget.is_finite() or max_budget < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                return Response(
                    {"detail": "max_budget must be a valid non-negative number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        projects = services.search_projects(
            query=request.query_params.get("q"),
            skill=request.query_params.get("skill"),
            category=request.query_params.get("category"),
            max_budget=max_budget,
        )

        # Students can browse published projects.
        # Clients can browse published projects and their own projects.
        role = str(getattr(request.user, "role", "")).lower()
        client_id = get_client_id(request)

        if role == "client" and client_id:
            if isinstance(projects, list):
                projects = [
                    project for project in projects
                    if (
                        project.status == Project.Status.PUBLISHED
                        or str(project.client_id) == client_id
                    )
                ]
            else:
                from django.db.models import Q

                projects = projects.filter(
                    Q(status=Project.Status.PUBLISHED)
                    | Q(client_id=client_id)
                )

        elif not getattr(request.user, "is_staff", False):
            if isinstance(projects, list):
                projects = [
                    project for project in projects
                    if project.status == Project.Status.PUBLISHED
                ]
            else:
                projects = projects.filter(
                    status=Project.Status.PUBLISHED
                )

        serializer = ProjectSerializer(projects, many=True)
        return Response(serializer.data)

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

        client_id = get_client_id(request)
        is_owner = (
            client_id is not None
            and str(project.client_id) == client_id
        )
        is_admin = getattr(request.user, "is_staff", False)

        if (
            project.status != Project.Status.PUBLISHED
            and not is_owner
            and not is_admin
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

    def delete(self, request, project_id):
        project = self.get_object(project_id)

        if project is None:
            return Response(
                {"detail": "Project not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_admin = getattr(request.user, "is_staff", False)

        if not is_admin:
            if not is_client(request):
                return Response(
                    {"detail": "Only the project owner or an admin can delete projects."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            client_id = get_client_id(request)

            if (
                client_id is None
                or str(project.client_id) != client_id
            ):
                return Response(
                    {"detail": "You cannot delete another client's project."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        project.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


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

        client_id = get_client_id(request)
        is_owner = (
            client_id is not None
            and str(project.client_id) == client_id
        )
        is_admin = getattr(request.user, "is_staff", False)

        if not is_owner and not is_admin:
            return Response(
                {"detail": "You cannot view this project's status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response({
            "id": str(project.id),
            "status": project.status,
        })
