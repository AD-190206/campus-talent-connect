"""Application & Assignment endpoints (API contract §8.3).

Identity always comes from the validated JWT. Client ownership of a project
is verified with the Project service, forwarding the caller's token.
"""
import uuid

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from . import services
from .api import ApiError, paginated, success
from .models import Application, Assignment
from .project_client import get_project, start_project
from .serializers import (
    ApplicationCreateSerializer,
    ApplicationSerializer,
    ApplicationUpdateSerializer,
    AssignmentSerializer,
)


# ---------------------------------------------------------------- helpers

def require_role(request, *roles):
    if request.user.role not in roles:
        raise ApiError(
            f"This action requires role: {', '.join(roles)}.",
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
        )


def auth_header(request):
    return request.headers.get("Authorization", "")


def uuid_param(request, name):
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise ApiError(
            "Invalid query parameter.",
            "VALIDATION_ERROR",
            details={"fields": {name: ["Must be a valid UUID."]}},
        )


def is_applicant(request, application):
    return (
        request.user.role == "STUDENT"
        and application.student_id == request.user.id
    )


def verify_project_owner(request, project_id):
    """Return the project if the caller is the client who owns it."""
    if request.user.role != "CLIENT":
        raise ApiError(
            "Only the client who owns the project can do this.",
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
        )

    project = get_project(project_id, auth_header(request))

    if str(project.get("client_id")) != str(request.user.id):
        raise ApiError(
            "You do not own this project.",
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
        )

    return project


def get_application_for_reader(request, pk):
    """Applicant, owning client or admin may read an application."""
    application = get_object_or_404(Application, id=pk)

    if request.user.role == "ADMIN" or is_applicant(request, application):
        return application

    if request.user.role == "CLIENT":
        verify_project_owner(request, application.project_id)
        return application

    raise ApiError(
        "You cannot access this application.",
        "FORBIDDEN",
        status.HTTP_403_FORBIDDEN,
    )


def get_application_for_owner_client(request, pk):
    application = get_object_or_404(Application, id=pk)
    verify_project_owner(request, application.project_id)
    return application


def get_application_for_applicant(request, pk):
    application = get_object_or_404(Application, id=pk)
    if not is_applicant(request, application):
        raise ApiError(
            "Only the applicant can do this.",
            "FORBIDDEN",
            status.HTTP_403_FORBIDDEN,
        )
    return application


def visible_assignments(user):
    if user.role == "ADMIN":
        return Assignment.objects.all()
    return Assignment.objects.filter(Q(student_id=user.id) | Q(client_id=user.id))


# ------------------------------------------------------------------ views

class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return success(
            {"service": "application-service", "status": "healthy"},
            "Health check successful",
        )


class ApplicationListCreateView(APIView):
    def get(self, request):
        """
        STUDENT: own applications (optionally filtered by project_id).
        CLIENT:  applications for a project they own (project_id required).
        ADMIN:   any, optionally filtered by project_id / student_id.
        """
        project_id = uuid_param(request, "project_id")
        student_id = uuid_param(request, "student_id")
        role = request.user.role

        if role == "STUDENT":
            if student_id and student_id != request.user.id:
                raise ApiError(
                    "Students can only list their own applications.",
                    "FORBIDDEN",
                    status.HTTP_403_FORBIDDEN,
                )
            qs = Application.objects.filter(student_id=request.user.id)
        elif role == "CLIENT":
            if not project_id:
                raise ApiError(
                    "project_id is required for clients.",
                    "VALIDATION_ERROR",
                    details={"fields": {"project_id": ["This parameter is required."]}},
                )
            verify_project_owner(request, project_id)
            qs = Application.objects.all()
            if student_id:
                qs = qs.filter(student_id=student_id)
        else:
            qs = Application.objects.all()
            if student_id:
                qs = qs.filter(student_id=student_id)

        if project_id:
            qs = qs.filter(project_id=project_id)

        app_status = request.query_params.get("status")
        if app_status:
            qs = qs.filter(status=app_status)

        return paginated(
            qs.order_by("-created_at", "id"),
            ApplicationSerializer,
            request.query_params,
            "Applications retrieved successfully",
        )

    def post(self, request):
        require_role(request, "STUDENT")

        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        project = get_project(data["project_id"], auth_header(request))
        if project.get("status") != "PUBLISHED":
            raise ApiError(
                "This project is not accepting applications.",
                "INVALID_STATE_TRANSITION",
            )

        application = services.create_application(
            student_id=request.user.id,
            project_id=data["project_id"],
            proposal=data["proposal"],
            resume_url=data.get("resume_url", ""),
        )

        return success(
            ApplicationSerializer(application).data,
            "Application submitted successfully",
            status.HTTP_201_CREATED,
        )


class ApplicationDetailView(APIView):
    def get(self, request, pk):
        application = get_application_for_reader(request, pk)
        return success(
            ApplicationSerializer(application).data,
            "Application retrieved successfully",
        )

    def _update(self, request, pk, partial):
        application = get_application_for_applicant(request, pk)
        serializer = ApplicationUpdateSerializer(
            application, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        updated = services.update_application(
            application, **serializer.validated_data
        )
        return success(
            ApplicationSerializer(updated).data,
            "Application updated successfully",
        )

    def put(self, request, pk):
        return self._update(request, pk, partial=False)

    def patch(self, request, pk):
        return self._update(request, pk, partial=True)


class ApplicationShortlistView(APIView):
    def post(self, request, pk):
        application = get_application_for_owner_client(request, pk)
        application = services.shortlist_application(application)
        return success(
            ApplicationSerializer(application).data,
            "Application shortlisted successfully",
        )


class ApplicationSelectView(APIView):
    def post(self, request, pk):
        application = get_object_or_404(Application, id=pk)
        project = verify_project_owner(request, application.project_id)

        if project.get("status") not in {"PUBLISHED", "IN_PROGRESS"}:
            raise ApiError(
                "Applicants can only be selected for a published project.",
                "INVALID_STATE_TRANSITION",
            )

        application, assignment = services.select_application(
            application,
            client_id=request.user.id,
            on_assigned=lambda _: start_project(
                application.project_id, auth_header(request)
            ),
        )

        return success(
            {
                "application": ApplicationSerializer(application).data,
                "assignment": AssignmentSerializer(assignment).data,
            },
            "Applicant selected and assignment created",
            status.HTTP_201_CREATED,
        )


class ApplicationRejectView(APIView):
    def post(self, request, pk):
        application = get_application_for_owner_client(request, pk)
        application = services.reject_application(application)
        return success(
            ApplicationSerializer(application).data,
            "Application rejected successfully",
        )


class ApplicationWithdrawView(APIView):
    def post(self, request, pk):
        application = get_application_for_applicant(request, pk)
        application = services.withdraw_application(application)
        return success(
            ApplicationSerializer(application).data,
            "Application withdrawn successfully",
        )


class AssignmentListView(APIView):
    def get(self, request):
        qs = visible_assignments(request.user)

        project_id = uuid_param(request, "project_id")
        if project_id:
            qs = qs.filter(project_id=project_id)

        assignment_status = request.query_params.get("status")
        if assignment_status:
            qs = qs.filter(status=assignment_status)

        return paginated(
            qs.order_by("-assigned_date", "id"),
            AssignmentSerializer,
            request.query_params,
            "Assignments retrieved successfully",
        )


class AssignmentDetailView(APIView):
    def get(self, request, pk):
        assignment = get_object_or_404(visible_assignments(request.user), id=pk)
        return success(
            AssignmentSerializer(assignment).data,
            "Assignment retrieved successfully",
        )


class AssignmentCompleteView(APIView):
    def post(self, request, pk):
        require_role(request, "CLIENT")
        assignment = get_object_or_404(
            Assignment.objects.filter(client_id=request.user.id), id=pk
        )
        assignment = services.complete_assignment(assignment)
        return success(
            AssignmentSerializer(assignment).data,
            "Assignment completed successfully",
        )
