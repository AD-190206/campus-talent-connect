import os

import requests


class PaymentServiceError(Exception):
    """Base error for Payment Service communication."""


class PaymentServiceUnavailableError(PaymentServiceError):
    """The Payment Service could not be reached or returned an error."""


def post_payment_request(path, payload):
    base_url = os.getenv("PAYMENT_SERVICE_URL", "").rstrip("/")

    if not base_url:
        raise PaymentServiceUnavailableError(
            "Payment Service URL is not configured."
        )

    if not path or path.startswith("/") or "://" in path:
        raise ValueError(
            "Provide a relative API path without a leading slash."
        )

    url = f"{base_url}/{path}"

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=3,
        )
    except requests.RequestException as exc:
        raise PaymentServiceUnavailableError(
            "Could not reach the Payment Service."
        ) from exc

    if response.status_code not in {200, 201, 202}:
        raise PaymentServiceUnavailableError(
            f"Payment Service returned HTTP {response.status_code}."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise PaymentServiceUnavailableError(
            "Payment Service returned invalid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise PaymentServiceUnavailableError(
            "Payment Service returned an unexpected data format."
        )

    return data