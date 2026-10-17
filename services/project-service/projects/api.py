from django.http import JsonResponse


def json_400(request, exception):
    return JsonResponse(
        {
            "error": {
                "code": "bad_request",
                "message": "Bad request.",
            }
        },
        status=400,
    )


def json_404(request, exception):
    return JsonResponse(
        {
            "error": {
                "code": "not_found",
                "message": "Resource not found.",
            }
        },
        status=404,
    )


def json_500(request):
    return JsonResponse(
        {
            "error": {
                "code": "internal_server_error",
                "message": "An internal server error occurred.",
            }
        },
        status=500,
    )
