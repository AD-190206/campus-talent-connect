from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
import math

from .serializers import (
    ApplicationCreateSerializer,
    ApplicationListSerializer,
    ApplicationUpdateSerializer,
    AssignmentSerializer,
)
from .services import (
    DuplicateApplicationError,
    create_application,
    update_application,
    get_applications_for_project,
    get_applications_for_student,
    get_application_by_id,
    shortlist_application,
    select_application,
    reject_application,
    withdraw_application,
    get_assignment_by_id,
    get_assignments_for_project,
    get_all_assignments,
)
from .project_client import get_project, update_project_status, ProjectServiceError
from .models import Application


def require_role(request, *roles):
    role = getattr(request, "user_role", None)
    if role not in roles:
        raise PermissionDenied(
            f"Access denied. Required role: {', '.join(roles)}. Your role: {role or 'unauthenticated'}."
        )


def success(data, message, http_status=status.HTTP_200_OK):
    return Response({"data": data, "message": message}, status=http_status)


def error(message, code, details=None, http_status=status.HTTP_400_BAD_REQUEST):
    return Response(
        {"error": message, "code": code, "details": details or {}},
        status=http_status,
    )


def paginate(queryset, serializer_class, request):
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
    except ValueError:
        return None, error("page and page_size must be integers.", "VALIDATION_ERROR",
                           http_status=status.HTTP_400_BAD_REQUEST)
    if page < 1 or page_size < 1 or page_size > 100:
        return None, error("page >= 1 and 1 <= page_size <= 100 required.", "VALIDATION_ERROR",
                           http_status=status.HTTP_400_BAD_REQUEST)
    total = queryset.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    items = queryset[(page - 1) * page_size: page * page_size]
    serializer = serializer_class(items, many=True)
    data = {
        "data": serializer.data,
        "message": "Resources retrieved successfully",
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }
    return data, None


class HealthView(APIView):
    def get(self, request):
        return success(
            {"service": "application-service", "status": "healthy"},
            "Health check successful",
        )


class ApplicationListCreateView(APIView):
    def get(self, request):
        project_id = request.query_params.get("project_id")
        student_id = request.query_params.get("student_id")

        if project_id:
            qs = get_applications_for_project(project_id)
        elif student_id:
            qs = get_applications_for_student(student_id)
        else:
            return error(
                "Provide either project_id or student_id as a query parameter.",
                "VALIDATION_ERROR",
            )

        data, err = paginate(qs, ApplicationListSerializer, request)
        if err:
            return err
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        require_role(request, "STUDENT")

        student_id = getattr(request, "user_id", None)
        if not student_id:
            return error("Authentication required.", "UNAUTHORIZED",
                         http_status=status.HTTP_401_UNAUTHORIZED)

        project_id = request.data.get("project_id")

        # Validate project exists and is PUBLISHED
        auth_header = request.headers.get("Authorization", "")
        try:
            project = get_project(project_id, auth_header)
        except ProjectServiceError as e:
            return error(e.message, e.code, http_status=e.http_status)

        if project.get("status") != "PUBLISHED":
            return error(
                "Project is not accepting applications.",
                "PROJECT_NOT_PUBLISHED",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        if Application.objects.filter(
            student_id=student_id, project_id=project_id
        ).exists():
            return error(
                "Student has already applied to this project.",
                "DUPLICATE_APPLICATION",
                http_status=status.HTTP_409_CONFLICT,
            )

        data = request.data.copy()
        data["student_id"] = student_id
        serializer = ApplicationCreateSerializer(data=data)
        if not serializer.is_valid():
            return error(
                "Validation failed.",
                "VALIDATION_ERROR",
                details={"fields": serializer.errors},
            )

        try:
            application = create_application(
                student_id=serializer.validated_data["student_id"],
                project_id=serializer.validated_data["project_id"],
                proposal=serializer.validated_data["proposal"],
                resume_url=serializer.validated_data.get("resume_url", ""),
            )
        except DuplicateApplicationError:
            return error(
                "Student has already applied to this project.",
                "DUPLICATE_APPLICATION",
                http_status=status.HTTP_409_CONFLICT,
            )

        return success(
            ApplicationCreateSerializer(application).data,
            "Application submitted successfully.",
            http_status=status.HTTP_201_CREATED,
        )


class ApplicationDetailView(APIView):
    def get(self, request, pk):
        application = get_application_by_id(pk)
        return success(ApplicationListSerializer(application).data, "Application retrieved.")

    def put(self, request, pk):
        require_role(request, "STUDENT")
        application = get_application_by_id(pk)
        serializer = ApplicationUpdateSerializer(application, data=request.data)
        if not serializer.is_valid():
            return error("Validation failed.", "VALIDATION_ERROR",
                         details={"fields": serializer.errors})
        updated = update_application(
            application_id=pk,
            proposal=serializer.validated_data.get("proposal"),
            resume_url=serializer.validated_data.get("resume_url"),
        )
        return success(ApplicationListSerializer(updated).data, "Application updated.")


class ApplicationShortlistView(APIView):
    def post(self, request, pk):
        require_role(request, "CLIENT", "ADMIN")
        try:
            application = shortlist_application(pk)
        except ValueError as e:
            return error(str(e), "INVALID_STATE_TRANSITION")
        return success(ApplicationListSerializer(application).data, "Application shortlisted.")


class ApplicationSelectView(APIView):
    def post(self, request, pk):
        require_role(request, "CLIENT", "ADMIN")

        # Fetch project to get client_id and verify ownership
        application = get_application_by_id(pk)
        auth_header = request.headers.get("Authorization", "")
        try:
            project = get_project(str(application.project_id), auth_header)
        except ProjectServiceError as e:
            return error(e.message, e.code, http_status=e.http_status)

        # Verify caller owns the project
        caller_id = str(getattr(request, "user_id", ""))
        if str(project.get("client_id")) != caller_id:
            return error(
                "You do not own this project.",
                "FORBIDDEN",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        client_id = project.get("client_id")

        try:
            application, assignment = select_application(pk, client_id=client_id)
        except ValueError as e:
            return error(str(e), "INVALID_STATE_TRANSITION")

        update_project_status(str(application.project_id), "IN_PROGRESS", auth_header)
        return success(
            {
                "application": ApplicationListSerializer(application).data,
                "assignment": AssignmentSerializer(assignment).data,
            },
            "Applicant selected and assignment created.",
            http_status=status.HTTP_201_CREATED,
        )


class ApplicationRejectView(APIView):
    def post(self, request, pk):
        require_role(request, "CLIENT", "ADMIN")
        try:
            application = reject_application(pk)
        except ValueError as e:
            return error(str(e), "INVALID_STATE_TRANSITION")
        return success(ApplicationListSerializer(application).data, "Application rejected.")


class ApplicationWithdrawView(APIView):
    def post(self, request, pk):
        require_role(request, "STUDENT")
        try:
            application = withdraw_application(pk)
        except ValueError as e:
            return error(str(e), "INVALID_STATE_TRANSITION")
        return success(ApplicationListSerializer(application).data, "Application withdrawn.")


class AssignmentListView(APIView):
    def get(self, request):
        project_id = request.query_params.get("project_id")

        if project_id:
            qs = get_assignments_for_project(project_id)
        else:
            qs = get_all_assignments()

        data, err = paginate(qs, AssignmentSerializer, request)
        if err:
            return err
        return Response(data, status=status.HTTP_200_OK)


class AssignmentDetailView(APIView):
    def get(self, request, pk):
        assignment = get_assignment_by_id(pk)
        return success(AssignmentSerializer(assignment).data, "Assignment retrieved.")

    def patch(self, request, pk):
        require_role(request, "CLIENT", "ADMIN")
        assignment = get_assignment_by_id(pk)
        new_status = request.data.get("status")
        allowed = ["active", "completed"]
        if new_status not in allowed:
            return error(
                f"Invalid status '{new_status}'. Allowed: {', '.join(allowed)}.",
                "VALIDATION_ERROR",
                details={"fields": {"status": f"Must be one of: {', '.join(allowed)}"}},
            )
        assignment.status = new_status
        assignment.save()
        return success(AssignmentSerializer(assignment).data, "Assignment updated.")


