from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler

class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "A required service is temporarily unavailable."
    default_code = "SERVICE_UNAVAILABLE"


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    # Let Django handle unexpected non-DRF exceptions normally.
    if response is None:
        return None

    if isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"
        message = "Request validation failed."
    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        code = "AUTHENTICATION_REQUIRED"
        message = "Authentication is required or invalid."
    elif isinstance(exc, PermissionDenied):
        code = "PERMISSION_DENIED"
        message = "You do not have permission to perform this action."
    elif isinstance(exc, NotFound):
        code = "NOT_FOUND"
        message = "The requested resource was not found."
    elif isinstance(exc, MethodNotAllowed):
        code = "METHOD_NOT_ALLOWED"
        message = "This HTTP method is not allowed."
    elif isinstance(exc, Throttled):
        code = "RATE_LIMITED"
        message = "Too many requests."
    elif isinstance(exc, APIException):
        code = getattr(exc, "default_code", "API_ERROR")
        message = str(exc.detail)
    else:
        code = "REQUEST_ERROR"
        message = "The request could not be completed."

    response.data = {
        "error": message,
        "code": code,
        "details": response.data,
    }

    return response
