import os

import requests


class PaymentServiceError(Exception):
    """Base error for Payment Service communication."""


class PaymentServiceUnavailableError(PaymentServiceError):
    """The Payment Service could not be reached or returned an invalid response."""


class PaymentServiceAuthorizationError(PaymentServiceError):
    """The Payment Service rejected the forwarded caller credentials."""


def _post_payment_request(path, payload, access_token):
    base_url = os.getenv("PAYMENT_SERVICE_URL", "").rstrip("/")

    if not base_url:
        raise PaymentServiceUnavailableError(
            "Payment Service URL is not configured."
        )

    if not path or path.startswith("/") or "://" in path:
        raise ValueError(
            "Provide a relative API path without a leading slash."
        )

    if not access_token:
        raise PaymentServiceAuthorizationError(
            "An authenticated access token is required."
        )

    url = f"{base_url}/{path}"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=3,
        )
    except requests.RequestException as exc:
        raise PaymentServiceUnavailableError(
            "Could not reach the Payment Service."
        ) from exc

    if response.status_code in {401, 403}:
        raise PaymentServiceAuthorizationError(
            "Payment Service rejected the caller's credentials."
        )

    if response.status_code not in {200, 201, 202}:
        raise PaymentServiceUnavailableError(
            f"Payment Service returned HTTP {response.status_code}."
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise PaymentServiceUnavailableError(
            "Payment Service returned invalid JSON."
        ) from exc

    if not isinstance(body, dict):
        raise PaymentServiceUnavailableError(
            "Payment Service returned an unexpected response format."
        )

    data = body.get("data")
    if not isinstance(data, dict):
        raise PaymentServiceUnavailableError(
            "Payment Service response is missing a valid data object."
        )

    return body


def post_payment_request(path, payload, access_token):
    """Create a payment request."""
    return _post_payment_request(path, payload, access_token)


def process_payment_request(payment_id, access_token):
    """Ask the Payment Service to process a pending payment."""
    return _post_payment_request(
        f"api/payments/{payment_id}/process/",
        {},
        access_token,
    )


def release_payment_request(payment_id, access_token):
    """Ask the Payment Service to release a successful payment."""
    return _post_payment_request(
        f"api/payments/{payment_id}/release/",
        {},
        access_token,
    )
