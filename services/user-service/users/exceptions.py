
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    # Let Django handle unexpected server errors normally.
    if response is None:
        return None

    original_data = response.data
    details = {}

    if isinstance(original_data, dict):
        # DRF validation errors are usually keyed by field name.
        if response.status_code == 400:
            details = {"fields": original_data}
        else:
            details = original_data

    if response.status_code == 400:
        code = "VALIDATION_ERROR"
        message = "The submitted data is invalid."
    elif response.status_code == 401:
        code = "UNAUTHORIZED"
        message = "Authentication is required or the credentials are invalid."
    elif response.status_code == 403:
        code = "FORBIDDEN"
        message = "You do not have permission to perform this action."
    elif response.status_code == 404:
        code = "NOT_FOUND"
        message = "The requested resource was not found."
    elif response.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
        message = "This HTTP method is not allowed."
    elif response.status_code == 429:
        code = "RATE_LIMITED"
        message = "Too many requests."
    else:
        code = "REQUEST_ERROR"
        message = "The request could not be completed."

    response.data = {
        "error": message,
        "code": code,
        "details": details,
    }

    return response
