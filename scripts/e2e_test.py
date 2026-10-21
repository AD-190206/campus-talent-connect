#!/usr/bin/env python3
"""End-to-end smoke test for Campus Talent Connect.

Runs the core workflow from the shared brief through the API gateway:

    register -> login -> create/publish project -> browse -> apply ->
    shortlist -> select (assignment) -> pay (mock) -> submit work ->
    approve (payment released) -> notifications -> reviews

Usage (stack must be running, e.g. `docker compose up --build`):

    python scripts/e2e_test.py [--base-url http://localhost:8000/api]

Uses only the Python standard library. Exits non-zero on the first failure.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, timedelta

BASE_URL = "http://localhost:8000/api"


class StepFailed(Exception):
    pass


def call(method, path, token=None, body=None, expect=200):
    """Send a request and return the parsed JSON body; check the status."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, method=method
    )
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except urllib.error.URLError as error:
        raise StepFailed(f"{method} {path}: cannot reach gateway ({error.reason})")

    try:
        payload = json.loads(raw) if raw else None
    except ValueError:
        raise StepFailed(f"{method} {path}: non-JSON response ({status}): {raw[:200]!r}")

    if status != expect:
        raise StepFailed(
            f"{method} {path}: expected HTTP {expect}, got {status}: "
            f"{json.dumps(payload, indent=2)}"
        )

    check_envelope(method, path, status, payload)
    return payload


def check_envelope(method, path, status, payload):
    where = f"{method} {path}"
    if not isinstance(payload, dict):
        raise StepFailed(f"{where}: body is not a JSON object")
    if status >= 400:
        for key in ("error", "code", "details"):
            if key not in payload:
                raise StepFailed(f"{where}: error envelope missing '{key}'")
        return
    if "data" not in payload or not payload.get("message"):
        raise StepFailed(f"{where}: success envelope missing data/message")
    if isinstance(payload["data"], list) and "pagination" not in payload:
        raise StepFailed(f"{where}: collection missing pagination")


def expect_equal(label, actual, expected):
    if actual != expected:
        raise StepFailed(f"{label}: expected {expected!r}, got {actual!r}")


STEP = 0


def step(title):
    global STEP
    STEP += 1
    print(f"[{STEP:2d}] {title}")


def prepay_assignment(c_token, assignment, student, suffix):
    """Contract §9.2 steps 2-3: the client pays before work is approved."""
    step("Client creates the payment (amount from project budget) and processes it (mock)")
    payment = call("POST", "/payments/", token=c_token, body={
        "assignment_id": assignment["id"],
        "payee_id": student["user_id"],
        "amount": "1.00",
        "idempotency_key": f"e2e-{suffix}",
    }, expect=201)["data"]
    expect_equal("payment.amount", payment["amount"], "1250.00")
    expect_equal("payment.payment_mode", payment["payment_mode"], "MOCK")
    payment = call("POST", f"/payments/{payment['id']}/process/", token=c_token, body={})["data"]
    expect_equal("payment.status", payment["status"], "SUCCESS")
    # Not releasable yet: no work has been submitted.
    call("POST", f"/payments/{payment['id']}/release/", token=c_token, body={}, expect=409)
    return payment


def run(prepay):
    suffix = uuid.uuid4().hex[:8]
    password = "Str0ngPassw0rd!"

    step("Gateway and service health")
    call("GET", "/health/")

    step("Register student and client")
    student = call("POST", "/auth/register/", body={
        "email": f"student-{suffix}@example.com",
        "password": password,
        "role": "STUDENT",
        "name": "Asha Student",
        "college": "CTC College",
        "skills": "Python, Django",
    }, expect=201)["data"]
    client = call("POST", "/auth/register/", body={
        "email": f"client-{suffix}@example.com",
        "password": password,
        "role": "CLIENT",
        "contact_person": "Ravi Client",
        "company_name": "Acme Ltd",
    }, expect=201)["data"]
    uuid.UUID(student["user_id"])
    uuid.UUID(client["user_id"])

    call("POST", "/auth/register/", body={
        "email": f"admin-{suffix}@example.com",
        "password": password,
        "role": "ADMIN",
    }, expect=400)

    step("Log in both users; refresh rotates tokens")
    s_login = call("POST", "/auth/login/", body={
        "email": student["email"], "password": password,
    })["data"]
    c_login = call("POST", "/auth/login/", body={
        "email": client["email"], "password": password,
    })["data"]
    s_token, c_token = s_login["access_token"], c_login["access_token"]
    expect_equal("token_type", s_login["token_type"], "Bearer")

    me = call("GET", "/auth/me/", token=s_token)["data"]
    expect_equal("me.user_id", me["user_id"], student["user_id"])

    refreshed = call("POST", "/auth/refresh/", body={
        "refresh_token": c_login["refresh_token"],
    })["data"]
    c_token = refreshed["access_token"]
    call("POST", "/auth/refresh/", body={
        "refresh_token": c_login["refresh_token"],
    }, expect=401)

    call("GET", "/projects/", expect=401)
    call("GET", f"/users/{client['user_id']}/", token=s_token, expect=403)
    profile = call("GET", f"/users/{student['user_id']}/profile/", token=s_token)["data"]
    expect_equal("profile.name", profile["name"], "Asha Student")

    step("Client creates and publishes a project")
    project = call("POST", "/projects/", token=c_token, body={
        "title": f"E2E landing page {suffix}",
        "description": "Build a responsive landing page.",
        "skills": ["React", "Tailwind"],
        "category": "Web",
        "budget": "1250.00",
        "deadline": (date.today() + timedelta(days=30)).isoformat(),
    }, expect=201)["data"]
    expect_equal("project.status", project["status"], "DRAFT")
    call("POST", "/projects/", token=s_token, body={}, expect=403)

    project = call("POST", f"/projects/{project['id']}/publish/", token=c_token)["data"]
    expect_equal("project.status", project["status"], "PUBLISHED")

    step("Student browses and searches projects")
    found = call("GET", f"/projects/?query={suffix}&page_size=5", token=s_token)
    expect_equal(
        "search result", [p["id"] for p in found["data"]], [project["id"]]
    )
    call("GET", "/projects/?page_size=500", token=s_token, expect=400)

    step("Student applies (duplicate is rejected)")
    application = call("POST", "/applications/", token=s_token, body={
        "project_id": project["id"],
        "proposal": "I have built similar pages before.",
    }, expect=201)["data"]
    expect_equal("application.student_id", application["student_id"], student["user_id"])
    call("POST", "/applications/", token=s_token, body={
        "project_id": project["id"], "proposal": "Again",
    }, expect=409)

    step("Client views applications for the project")
    apps = call("GET", f"/applications/?project_id={project['id']}", token=c_token)
    expect_equal("application count", apps["pagination"]["total"], 1)
    call("GET", f"/applications/{application['id']}/", token=c_token)

    step("Client shortlists the application")
    shortlisted = call(
        "POST", f"/applications/{application['id']}/shortlist/", token=c_token
    )["data"]
    expect_equal("application.status", shortlisted["status"], "shortlisted")

    step("Client selects the student -> assignment created")
    selected = call(
        "POST", f"/applications/{application['id']}/select/", token=c_token,
        expect=201,
    )["data"]
    assignment = selected["assignment"]
    expect_equal("assignment.status", assignment["status"], "active")
    expect_equal("assignment.student_id", assignment["student_id"], student["user_id"])
    expect_equal("assignment.client_id", assignment["client_id"], client["user_id"])
    status = call("GET", f"/projects/{project['id']}/status/", token=c_token)["data"]
    expect_equal("project.status", status["status"], "IN_PROGRESS")
    call("GET", f"/assignments/{assignment['id']}/", token=s_token)

    payment = None
    if prepay:
        payment = prepay_assignment(c_token, assignment, student, suffix)

    step("Student creates and submits a deliverable")
    work = call("POST", "/work/", token=s_token, body={
        "assignment_id": assignment["id"],
        "project_id": project["id"],
        "title": "Landing page v1",
        "description": "First version.",
    }, expect=201)["data"]
    call("PATCH", f"/work/{work['id']}/", token=s_token, body={
        "submission_url": "https://example.com/landing-v1",
    })
    work = call("POST", f"/work/{work['id']}/submit/", token=s_token, body={})["data"]
    expect_equal("work.status", work["status"], "SUBMITTED")

    step("Client reviews the deliverable and requests a revision")
    listed = call("GET", f"/work/?assignment_id={assignment['id']}", token=c_token)
    expect_equal("work count", listed["pagination"]["total"], 1)
    call("POST", f"/work/{work['id']}/approve/", token=s_token, body={}, expect=403)
    work = call("POST", f"/work/{work['id']}/reject/", token=c_token, body={
        "feedback": "Please make the hero section responsive.",
    })["data"]
    expect_equal("work.status", work["status"], "REVISION_REQUESTED")
    work = call("POST", f"/work/{work['id']}/submit/", token=s_token, body={})["data"]

    step("Client approves -> payment released, project and assignment completed")
    approved = call("POST", f"/work/{work['id']}/approve/", token=c_token, body={})["data"]
    expect_equal("work.status", approved["status"], "APPROVED")
    expect_equal("payment.status", approved["payment"]["status"], "RELEASED")
    if payment is not None:
        expect_equal("payment.id", approved["payment"]["id"], payment["id"])
    payment = approved["payment"]
    call("POST", f"/work/{work['id']}/approve/", token=c_token, body={})

    released = call("GET", f"/payments/{payment['id']}/", token=s_token)["data"]
    expect_equal("payment.status", released["status"], "RELEASED")
    status = call("GET", f"/projects/{project['id']}/status/", token=c_token)["data"]
    expect_equal("project.status", status["status"], "COMPLETED")
    completed = call("GET", f"/assignments/{assignment['id']}/", token=s_token)["data"]
    expect_equal("assignment.status", completed["status"], "completed")

    step("Student receives a payment notification")
    notes = call("GET", "/notifications/", token=s_token)["data"]
    events = {n["event"] for n in notes}
    if "PAYMENT_RELEASED" not in events:
        raise StepFailed(f"student notifications missing PAYMENT_RELEASED: {events}")
    history = call("GET", "/payments/history/", token=s_token)
    expect_equal("student payment history", history["pagination"]["total"], 1)

    step("Client and student submit reviews")
    call("POST", "/reviews/", token=c_token, body={
        "assignment_id": assignment["id"],
        "reviewee_id": student["user_id"],
        "rating": 5,
        "comment": "Great work.",
    }, expect=201)
    review = call("POST", "/reviews/", token=s_token, body={
        "assignment_id": assignment["id"],
        "reviewee_id": client["user_id"],
        "rating": 4,
        "comment": "Clear requirements.",
    }, expect=201)["data"]
    call("POST", "/reviews/", token=s_token, body={
        "assignment_id": assignment["id"],
        "reviewee_id": client["user_id"],
        "rating": 4,
    }, expect=400)
    call("GET", f"/reviews/{review['id']}/", token=c_token)
    reviews = call("GET", "/reviews/", token=s_token)
    expect_equal("student review count", reviews["pagination"]["total"], 2)

    step("Logout revokes the refresh token")
    call("POST", "/auth/logout/", body={"refresh_token": s_login["refresh_token"]})
    call("POST", "/auth/refresh/", body={"refresh_token": s_login["refresh_token"]}, expect=401)

    step("Unknown routes return the JSON error envelope")
    call("GET", "/does-not-exist/", expect=404)


def main():
    global BASE_URL
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=BASE_URL)
    BASE_URL = parser.parse_args().base_url.rstrip("/")

    global STEP
    try:
        for prepay, label in (
            (True, "client pays before approval"),
            (False, "approval creates, processes and releases the payment"),
        ):
            STEP = 0
            print(f"\n=== Scenario: {label} ===")
            run(prepay)
    except StepFailed as failure:
        print(f"\nFAILED: {failure}")
        return 1

    print("\nAll end-to-end steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
