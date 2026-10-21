"""Translate every error into the common envelope (API contract §6.2)."""
import logging

from django.http import Http404, JsonResponse
from rest_framework import status
from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

STATUS_CODES = {
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have permission to perform this action."),
    404: ("NOT_FOUND", "The requested resource was not found."),
    405: ("METHOD_NOT_ALLOWED", "Method not allowed."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type."),
    429: ("RATE_LIMITED", "Too many requests."),
}


def error_body(message, code, details=None):
    return {"error": message, "code": code, "details": details or {}}


def custom_exception_handler(exc, context):
    if isinstance(exc, Http404):
        return Response(
            error_body("The requested resource was not found.", "NOT_FOUND"),
            status=status.HTTP_404_NOT_FOUND,
        )

    response = drf_exception_handler(exc, context)

    if response is None:
        logger.error("Unhandled exception", exc_info=exc)
        return Response(
            error_body("An unexpected error occurred.", "INTERNAL_SERVER_ERROR"),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, ValidationError):
        details = (
            {"fields": exc.detail} if isinstance(exc.detail, dict) else {}
        )
        body = error_body("Request validation failed.", "VALIDATION_ERROR", details)
    elif isinstance(exc, ParseError):
        body = error_body("Malformed request body.", "VALIDATION_ERROR")
    else:
        code, default_message = STATUS_CODES.get(
            response.status_code, ("REQUEST_ERROR", "Request failed.")
        )
        detail = getattr(exc, "detail", None)
        body = error_body(str(detail) if detail else default_message, code)

    response.data = body
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
