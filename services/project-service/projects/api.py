"""Common response envelopes, pagination and error handling.

Implements sections 6 and 7 of API_CONTRACT.md for the project service.
"""
import logging
import math

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import JsonResponse
from rest_framework import status
from rest_framework.exceptions import (
    ParseError,
    ValidationError as DRFValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .services import InvalidStateTransition, NotProjectOwner

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

STATUS_CODES = {
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have permission to perform this action."),
    404: ("NOT_FOUND", "The requested resource was not found."),
    405: ("METHOD_NOT_ALLOWED", "Method not allowed."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type."),
    429: ("RATE_LIMITED", "Too many requests."),
}


class ApiError(Exception):
    """Raise anywhere in a view to return the common error envelope."""

    def __init__(
        self,
        message,
        code,
        http_status=status.HTTP_400_BAD_REQUEST,
        details=None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.details = details or {}


# ------------------------------------------------------------- envelopes

def error_body(message, code, details=None):
    return {"error": message, "code": code, "details": details or {}}


def success(data, message, http_status=status.HTTP_200_OK):
    return Response(
        {"data": data, "message": message}, status=http_status
    )


def collection(data, message, pagination):
    return Response(
        {"data": data, "message": message, "pagination": pagination},
        status=status.HTTP_200_OK,
    )


# ------------------------------------------------------------ pagination

def _page_param(params, name, default, maximum=None):
    raw = params.get(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 0

    if value < 1 or (maximum is not None and value > maximum):
        limit = f" and at most {maximum}" if maximum else ""
        raise ApiError(
            "Invalid pagination parameter.",
            "VALIDATION_ERROR",
            details={
                "fields": {
                    name: [f"Must be an integer of at least 1{limit}."]
                }
            },
        )

    return value


def paginate(queryset, params):
    """Return (items, pagination) for the page and page_size params."""
    page = _page_param(params, "page", 1)
    page_size = _page_param(
        params, "page_size", DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
    )

    total = queryset.count()
    total_pages = math.ceil(total / page_size) if total else 0
    offset = (page - 1) * page_size
    items = list(queryset[offset:offset + page_size])

    return items, {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


# -------------------------------------------------------- error handling

def _messages(value):
    if isinstance(value, dict):
        return [
            f"{key}: {message}"
            for key, item in value.items()
            for message in _messages(item)
        ]
    if isinstance(value, (list, tuple)):
        return [message for item in value for message in _messages(item)]
    return [str(value)]


def _field_errors(errors):
    return {str(field): _messages(msgs) for field, msgs in errors.items()}


def _validation(message, fields=None):
    details = {"fields": fields} if fields else {}
    return Response(
        error_body(message, "VALIDATION_ERROR", details),
        status=status.HTTP_400_BAD_REQUEST,
    )


def exception_handler(exc, context):
    """Translate every exception into the common error envelope."""
    if isinstance(exc, ApiError):
        return Response(
            error_body(exc.message, exc.code, exc.details),
            status=exc.http_status,
        )

    # Order matters: both are subclasses of Django's ValidationError.
    if isinstance(exc, NotProjectOwner):
        return Response(
            error_body(" ".join(exc.messages), "FORBIDDEN"),
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, InvalidStateTransition):
        return Response(
            error_body(" ".join(exc.messages), "INVALID_STATE_TRANSITION"),
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "error_dict"):
            return _validation(
                "Validation failed.", _field_errors(exc.message_dict)
            )
        return _validation(" ".join(exc.messages))

    response = drf_exception_handler(exc, context)

    if response is None:
        logger.error("Unhandled exception", exc_info=exc)
        return Response(
            error_body(
                "An unexpected error occurred.", "INTERNAL_SERVER_ERROR"
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, DRFValidationError):
        if isinstance(exc.detail, dict):
            body = error_body(
                "Validation failed.",
                "VALIDATION_ERROR",
                {"fields": _field_errors(exc.detail)},
            )
        else:
            body = error_body(
                " ".join(_messages(exc.detail)), "VALIDATION_ERROR"
            )
    elif isinstance(exc, ParseError):
        body = error_body("Malformed request body.", "VALIDATION_ERROR")
    else:
        code, default_message = STATUS_CODES.get(
            response.status_code, ("REQUEST_ERROR", "Request failed.")
        )
        detail = getattr(exc, "detail", None)
        body = error_body(str(detail) if detail else default_message, code)

    # Keep headers such as WWW-Authenticate; only replace the body.
    response.data = body
    return response


def json_400(request, exception=None):
    return JsonResponse(
        error_body("The request could not be processed.", "VALIDATION_ERROR"),
        status=400,
    )


def json_404(request, exception=None):
    return JsonResponse(
        error_body(
            "The requested resource was not found.", "NOT_FOUND"
        ),
        status=404,
    )


def json_500(request):
    return JsonResponse(
        error_body("An unexpected error occurred.", "INTERNAL_SERVER_ERROR"),
        status=500,
    )