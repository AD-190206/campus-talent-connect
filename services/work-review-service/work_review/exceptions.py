import logging

from django.http import Http404, JsonResponse
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "A required service is temporarily unavailable."
    default_code = "UPSTREAM_SERVICE_ERROR"


def error_body(message, code, details=None):
    return {"error": message, "code": code, "details": details or {}}


def custom_exception_handler(exc, context):
    """Translate every error into the common envelope (API contract §6.2)."""
    if isinstance(exc, Http404):
        exc = NotFound()

    response = drf_exception_handler(exc, context)

    if response is None:
        logger.error("Unhandled exception", exc_info=exc)
        return Response(
            error_body("An unexpected error occurred.", "INTERNAL_SERVER_ERROR"),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    details = {}

    if isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"
        message = "Request validation failed."
        if isinstance(exc.detail, dict):
            details = {"fields": exc.detail}
        else:
            message = " ".join(str(item) for item in exc.detail) or message
    elif isinstance(exc, ParseError):
        code = "VALIDATION_ERROR"
        message = "Malformed request body."
    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        code = "UNAUTHORIZED"
        message = str(exc.detail)
    elif isinstance(exc, PermissionDenied):
        code = "FORBIDDEN"
        message = str(exc.detail)
    elif isinstance(exc, NotFound):
        code = "NOT_FOUND"
        message = str(exc.detail)
    elif isinstance(exc, MethodNotAllowed):
        code = "METHOD_NOT_ALLOWED"
        message = "This HTTP method is not allowed."
    elif isinstance(exc, Throttled):
        code = "RATE_LIMITED"
        message = "Too many requests."
    else:
        code = getattr(exc, "default_code", "REQUEST_ERROR").upper()
        message = str(getattr(exc, "detail", "")) or "The request could not be completed."

    response.data = error_body(message, code, details)
    return response


def json_404(request, exception=None):
    return JsonResponse(
        error_body("The requested resource was not found.", "NOT_FOUND"),
        status=404,
    )


def json_500(request):
    return JsonResponse(
        error_body("An unexpected error occurred.", "INTERNAL_SERVER_ERROR"),
        status=500,
    )
