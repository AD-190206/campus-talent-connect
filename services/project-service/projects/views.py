from django.db.models import Q
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from . import services
from .api import collection, paginate, success
from .models import Project
from .serializers import ProjectSerializer


# ---------------------------------------------------------------- helpers

def get_client_id(user):
    """The acting user's UUID, taken from the validated JWT."""
    user_id = getattr(user, "id", None)

    if user_id is None:
        raise PermissionDenied("The authenticated user has no identifier.")

    return user_id


def _role(user):
    return str(getattr(user, "role", "")).upper()


def is_client(user):
    return _role(user) == "CLIENT"


def is_admin(user):
    return _role(user) == "ADMIN"


def is_owner(user, project):
    return is_client(user) and str(project.client_id) == str(
        get_client_id(user)
    )


def can_view(user, project):
    """Admins and owners see everything; others see non-draft projects."""
    if is_admin(user) or is_owner(user, project):
        return True
    return project.status != Project.Status.DRAFT


def get_visible_project(user, project_id):
    """Fetch a project, hiding other users' drafts behind a 404."""
    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        raise NotFound("Project not found.")

    if not can_view(user, project):
        raise NotFound("Project not found.")

    return project


def visible_projects(user):
    """Projects the user may see in lists and searches."""
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
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return success(
            {"service": "project-service", "status": "healthy"},
            "Health check successful",
        )


class ProjectListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        projects = services.search_projects(
            queryset=visible_projects(request.user),
            query=request.query_params.get("query"),
            skill=request.query_params.get("skill"),
            category=request.query_params.get("category"),
            max_budget=request.query_params.get("max_budget"),
        ).order_by("-created_at", "id")

        items, pagination = paginate(projects, request.query_params)

        return collection(
            ProjectSerializer(items, many=True).data,
            "Projects retrieved successfully",
            pagination,
        )

    def post(self, request):
        if not is_client(request.user):
            raise PermissionDenied("Only clients can create projects.")

        serializer = ProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        project = services.create_project(
            client_id=get_client_id(request.user),
            **serializer.validated_data,
        )

        return success(
            ProjectSerializer(project).data,
            "Project created successfully",
            201,
        )


class ProjectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_visible_project(request.user, project_id)

        return success(
            ProjectSerializer(project).data,
            "Project retrieved successfully",
        )

    def _update(self, request, project_id):
        if not is_client(request.user):
            raise PermissionDenied("Only clients can edit projects.")

        project = get_visible_project(request.user, project_id)

        serializer = ProjectSerializer(
            project, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        updated = services.update_project(
            project=project,
            client_id=get_client_id(request.user),
            **serializer.validated_data,
        )

        return success(
            ProjectSerializer(updated).data,
            "Project updated successfully",
        )

    def put(self, request, project_id):
        return self._update(request, project_id)

    def patch(self, request, project_id):
        return self._update(request, project_id)

    def delete(self, request, project_id):
        project = get_visible_project(request.user, project_id)

        if not (is_admin(request.user) or is_owner(request.user, project)):
            raise PermissionDenied(
                "Only the owning client or an admin can delete a project."
            )

        deleted_id = str(project.id)
        services.delete_project(project=project)

        return success({"id": deleted_id}, "Project deleted successfully")


class PublishProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        if not is_client(request.user):
            raise PermissionDenied("Only clients can publish projects.")

        project = get_visible_project(request.user, project_id)

        project = services.publish_project(
            project=project, client_id=get_client_id(request.user)
        )

        return success(
            ProjectSerializer(project).data,
            "Project published successfully",
        )


class StartProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        if not is_client(request.user):
            raise PermissionDenied("Only the owning client can start a project.")

        project = get_visible_project(request.user, project_id)

        project = services.start_project(
            project=project, client_id=get_client_id(request.user)
        )

        return success(
            ProjectSerializer(project).data,
            "Project started successfully",
        )


class CompleteProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        if not is_client(request.user):
            raise PermissionDenied(
                "Only the owning client can complete a project."
            )

        project = get_visible_project(request.user, project_id)

        project = services.complete_project(
            project=project, client_id=get_client_id(request.user)
        )

        return success(
            ProjectSerializer(project).data,
            "Project completed successfully",
        )


class CloseProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        if not (is_client(request.user) or is_admin(request.user)):
            raise PermissionDenied(
                "Only the owning client or an admin can close a project."
            )

        project = get_visible_project(request.user, project_id)

        project = services.close_project(
            project=project,
            client_id=get_client_id(request.user),
            acting_as_admin=is_admin(request.user),
        )

        return success(
            ProjectSerializer(project).data,
            "Project closed successfully",
        )


class ProjectStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = get_visible_project(request.user, project_id)

        if not (is_admin(request.user) or is_owner(request.user, project)):
            raise PermissionDenied(
                "You do not have permission to view this status."
            )

        return success(
            {
                "id": str(project.id),
                "client_id": str(project.client_id),
                "title": project.title,
                "status": project.status,
                "budget": str(project.budget),
            },
            "Project status retrieved successfully",
        )