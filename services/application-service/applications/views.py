from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import (
    ApplicationCreateSerializer,
    ApplicationListSerializer,
    ApplicationUpdateSerializer,
    ApplicationStatusUpdateSerializer,
    ApplicationWithdrawSerializer,
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


class HealthView(APIView):
    def get(self, request):
        return Response({"service": "application-service", "status": "running"})


class ApplicationListCreateView(APIView):
    """
    GET  /api/applications/?project_id=X  → business sees all applicants
    GET  /api/applications/?student_id=X  → student sees their applications
    POST /api/applications/               → student submits an application
    """

    def get(self, request):
        project_id = request.query_params.get("project_id")
        student_id = request.query_params.get("student_id")

        if project_id:
            applications = get_applications_for_project(project_id)
        elif student_id:
            applications = get_applications_for_student(student_id)
        else:
            return Response(
                {"error": "Provide either project_id or student_id as a query parameter."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ApplicationListSerializer(applications, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ApplicationCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            application = create_application(
                student_id=serializer.validated_data["student_id"],
                project_id=serializer.validated_data["project_id"],
                proposal=serializer.validated_data["proposal"],
                resume_url=serializer.validated_data.get("resume_url", ""),
            )
        except DuplicateApplicationError:
            return Response(
                {
                    "error": "Student has already applied to this project.",
                    "code":  "DUPLICATE_APPLICATION",
                },
                status=status.HTTP_409_CONFLICT
            )

        return Response(
            ApplicationCreateSerializer(application).data,
            status=status.HTTP_201_CREATED
        )


class ApplicationDetailView(APIView):
    """
    GET /api/applications/<id>/  → get single application
    PUT /api/applications/<id>/  → student updates proposal/resume
    """

    def get(self, request, pk):
        application = get_application_by_id(pk)
        serializer = ApplicationListSerializer(application)
        return Response(serializer.data)

    def put(self, request, pk):
        application = get_application_by_id(pk)
        serializer = ApplicationUpdateSerializer(application, data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated = update_application(
            application_id=pk,
            proposal=serializer.validated_data.get("proposal"),
            resume_url=serializer.validated_data.get("resume_url"),
        )

        return Response(ApplicationListSerializer(updated).data)


class ApplicationShortlistView(APIView):
    def post(self, request, pk):
        try:
            application = shortlist_application(pk)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ApplicationListSerializer(application).data)


class ApplicationRejectView(APIView):
    def post(self, request, pk):
        try:
            application = reject_application(pk)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ApplicationListSerializer(application).data)


class ApplicationSelectView(APIView):
    """
    POST /api/applications/<id>/select/  → business selects → auto-creates assignment
    """

    def post(self, request, pk):
        try:
            application, assignment = select_application(pk)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "application": ApplicationListSerializer(application).data,
            "assignment":  AssignmentSerializer(assignment).data,
        }, status=status.HTTP_201_CREATED)


class ApplicationRejectView(APIView):
    """
    POST /api/applications/<id>/reject/  → business rejects
    """

    def post(self, request, pk):
        application = reject_application(pk)
        return Response(ApplicationListSerializer(application).data)


class ApplicationWithdrawView(APIView):
    """
    POST /api/applications/<id>/withdraw/  → student withdraws
    """

    def post(self, request, pk):
        try:
            application = withdraw_application(pk)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ApplicationListSerializer(application).data)


class AssignmentListView(APIView):
    """
    GET /api/assignments/              → all assignments
    GET /api/assignments/?project_id=X → assignments for a project
    """

    def get(self, request):
        project_id = request.query_params.get("project_id")

        if project_id:
            assignment = get_assignments_for_project(project_id)
            if not assignment:
                return Response(
                    {"error": "No assignment found for this project."},
                    status=status.HTTP_404_NOT_FOUND
                )
            return Response(AssignmentSerializer(assignment).data)

        assignments = get_all_assignments()
        return Response(AssignmentSerializer(assignments, many=True).data)


class AssignmentDetailView(APIView):
    """
    GET /api/assignments/<id>/  → used by Person 4 and Person 5
    """

    def get(self, request, pk):
        assignment = get_assignment_by_id(pk)
        return Response(AssignmentSerializer(assignment).data)