# Campus Talent Connect — Work & Review Service Context

**Last updated:** 15 October 2026  
**Owner:** Person 4 — Work & Review Service  
**Git branch:** `feature/work-review-service`  
**Latest implementation commit:** `204fa14`  
**Repository:** https://github.com/AD-190206/campus-talent-connect

## 1. Purpose of This File

This document records the current implementation state of the Work & Review Service, the tests run, known limitations, dependencies on other team members, and the remaining work.

Use it as the starting context when resuming development in a new ChatGPT conversation or handing the service to another developer.

This describes the state reached during the work session. The service is not yet fully integrated with the other microservices.

## 2. Overall Project Architecture

Campus Talent Connect is a student freelance marketplace.

The core workflow is:

1. A user registers and logs in.
2. A client creates a project.
3. A student applies to a project.
4. The client selects a student and an assignment is created.
5. The student submits work.
6. The client approves the work or requests revisions.
7. The Payment & Notification Service handles payment processing.
8. The participants can review one another.

### Services and local development ports

| Component | Port | Responsibility |
|---|---:|---|
| Next.js frontend | 3000 | User interface |
| Nginx API gateway | 8000 | Routes browser API requests |
| User & Authentication Service | 8001 | Registration, login, JWT, profiles and roles |
| Project Management Service | 8002 | Projects, search and project lifecycle |
| Application & Assignment Service | 8003 | Applications, selection and assignments |
| Work & Review Service | 8004 | Deliverables, submission, approval workflow and reviews |
| Payment & Notification Service | 8005 | Payments, transactions and notifications |

Browser requests should use the gateway, for example `http://localhost:8000/api/...`, rather than calling internal service URLs directly.

### Database boundaries

A single PostgreSQL instance hosts logically separate databases:

- `ctc_users`
- `ctc_projects`
- `ctc_applications`
- `ctc_work_reviews`
- `ctc_payments`

Each service owns its database. Do not introduce cross-service database queries, Django model imports, or foreign keys to another service's models. Cross-service references use UUIDs and REST APIs.

### Important payment boundary

The Work & Review Service must not mark a payment as paid merely because a deliverable is approved. Payment state and payment processing belong to the Payment & Notification Service.

## 3. Work & Review Service Implementation

Location: `services/work-review-service/`

Important files:

| File | Responsibility |
|---|---|
| `config/settings.py` | Django and DRF settings, authentication and permissions |
| `work_review/models.py` | Deliverable and Review database models |
| `work_review/serializers.py` | Serialization and validation |
| `work_review/views.py` | API endpoint behavior |
| `work_review/urls.py` | API routes |
| `work_review/authentication.py` | JWT authentication |
| `work_review/assignment_client.py` | REST client for the Application & Assignment Service |
| `work_review/payment_client.py` | REST client for the Payment & Notification Service |
| `work_review/migrations/0001_initial.py` | Initial database migration |
| `work_review/tests.py` | Automated tests |

### 3.1 Deliverable model

A deliverable represents work submitted by a student for an assignment.

Fields include:

- `id`: UUID primary key.
- `assignment_id`: UUID reference to the assignment.
- `student_id`: UUID reference to the student.
- `project_id`: UUID reference to the project.
- `title`: Deliverable title.
- `description`: Optional description.
- `submission_url`: URL of submitted work.
- `status`: Current deliverable status.
- `feedback`: Review feedback.
- `submitted_at`: Submission timestamp.
- `reviewed_at`: Review timestamp.
- `payment_requested`: Boolean tracking whether a payment request has been recorded.
- `created_at` and `updated_at`: Timestamps.

Available status values:

- `DRAFT`
- `SUBMITTED`
- `REVISION_REQUESTED`
- `APPROVED`

The model includes indexes for assignment/status and student/status queries. The default ordering is by most recently updated.

### 3.2 Review model

A review records feedback and a rating between two participants for an assignment.

Fields include:

- `id`: UUID primary key.
- `assignment_id`: UUID reference to the assignment.
- `reviewer_id`: UUID of the reviewer.
- `reviewee_id`: UUID of the person being reviewed.
- `reviewer_role`: `STUDENT` or `CLIENT`.
- `rating`: Integer from 1 through 5.
- `comment`: Optional text.
- `created_at`: Timestamp.

A database uniqueness constraint on `(assignment_id, reviewer_id)` prevents a reviewer from creating multiple reviews for the same assignment.

Rating validation enforces the range 1–5. Self-review is rejected by serializer validation.

## 4. Authentication and Authorization

File: `work_review/authentication.py`

The custom DRF authentication class:

1. Reads the `Authorization` header.
2. Expects a Bearer token.
3. Reads the `JWT_SECRET_KEY` environment variable.
4. Decodes the token using HS256.
5. Checks token expiry and invalid-token errors.
6. Extracts `user_id` and `role`.
7. Accepts the roles `STUDENT`, `CLIENT`, and `ADMIN`.
8. Exposes the authenticated identity through a lightweight `JWTUser` object.

The REST framework settings configure this JWT authentication class and use `IsAuthenticated` as the default permission.

Endpoints that need public access, such as health checks, must explicitly override the default permission.

**Integration caveat:** The expected algorithm, secret variable, identity claim, and role values still need confirmation from Person 1, who owns the User & Authentication Service. Do not assume the JWT contract is finalized until both services have been checked against the same contract.

## 5. Implemented API Routes

The service routes include the following endpoints.

| Method | Route | Current purpose |
|---|---|---|
| GET | `/api/health/` | Health check |
| GET | `/api/work/` | List work visible to the authenticated user |
| POST | `/api/work/` | Create a deliverable |
| GET | `/api/work/{work_id}/` | Retrieve a deliverable |
| PUT | `/api/work/{work_id}/` | Update a deliverable, subject to status validation |
| POST | `/api/work/{work_id}/submit/` | Submit a deliverable |
| POST | `/api/work/{work_id}/approve/` | Approval endpoint; currently blocked by ownership verification |
| POST | `/api/work/{work_id}/reject/` | Revision/rejection route; verify the exact behavior and contract before treating it as complete |
| GET | `/api/reviews/` | List reviews visible to the authenticated user |
| POST | `/api/reviews/` | Create a review |
| GET | `/api/reviews/{review_id}/` | Retrieve an individual review |

The shared API contract is in `docs/api/API_CONTRACT.md`. Reconcile the implemented routes with that document before final integration.

The documented contract includes POST `/api/work/`, GET/PUT `/api/work/{work_id}/`, submit/approve/reject actions, POST `/api/reviews/`, and GET `/api/reviews/{review_id}/`.

The two collection GET endpoints are implemented in the service but were not listed in the Work & Review section of the shared contract at the time of this handover.

## 6. Current Endpoint Behavior and Business Rules

### Work listing and creation

- Students see their own work.
- Administrators can see all work.
- Clients do not receive work through the current student-facing list/detail behavior.
- Only students can create work.
- The authenticated student's ID is used when creating a deliverable rather than trusting a client-supplied student identity.

### Work retrieval and editing

- Students can retrieve their own deliverables.
- Administrators can retrieve deliverables.
- Another student's deliverable is hidden from that student.
- Editing is allowed only when status is `DRAFT` or `REVISION_REQUESTED`.
- Submitted or approved work cannot be edited through the normal update serializer.

### Work submission

The submit endpoint:

- Requires the owning student.
- Requires a submission URL.
- Accepts work in `DRAFT` or `REVISION_REQUESTED`.
- Changes the status to `SUBMITTED`.
- Records the submission timestamp.
- Rejects submissions by another student.
- Rejects resubmission of work already submitted.

UUID/string comparisons are normalized where needed.

### Client approval and revision requests

The approval and revision-request endpoints perform basic existence and role checks.

**Important known limitation:** Client ownership verification is not integrated. A client request currently receives HTTP 503 with an ownership-verification-unavailable error instead of proceeding with approval or requesting revisions. This is intentional fail-closed behavior; it prevents an unverified client from acting on another client's assignment.

The assignment/project ownership lookup must be implemented before these workflows can be considered complete.

### Reviews

- Only students and clients can create reviews.
- The authenticated identity supplies `reviewer_id` and `reviewer_role`.
- User-supplied reviewer identity is not trusted.
- Ratings must be 1–5.
- Self-reviews are rejected.
- Duplicate reviews for the same assignment by the same reviewer are rejected.
- Users see reviews associated with themselves as reviewer or reviewee; administrators can see all reviews.

Review creation still needs the final assignment-participation and completion rules agreed upon by the team. Do not assume that every review is already restricted to a completed assignment unless that rule is explicitly enforced.

## 7. Inter-Service Client Foundations

### 7.1 Assignment client

File: `work_review/assignment_client.py`

The helper reads `APPLICATION_SERVICE_URL` and attempts:

`GET {APPLICATION_SERVICE_URL}/api/assignments/{assignment_id}/`

It has distinct exceptions for a missing assignment and for service communication/unexpected-response failures. It uses a 3-second timeout, handles request exceptions, validates the HTTP status, and requires a JSON object response.

The helper is a foundation, not a completed integration. The assignment endpoint, response fields, authentication requirements, and status semantics must be confirmed with Person 3.

### 7.2 Payment client

File: `work_review/payment_client.py`

The helper reads `PAYMENT_SERVICE_URL` and posts a JSON payload to a supplied relative path. It:

- Rejects empty or absolute/invalid paths.
- Uses a 3-second timeout.
- Handles request exceptions.
- Accepts HTTP 200, 201, or 202.
- Parses the response as a JSON object.
- Raises a service-specific exception for unexpected responses.

The payment endpoint and payload are not yet wired into the approval flow. Do not invent an endpoint or payload. Obtain the API contract from Person 5 first.

### 7.3 Docker environment

The root `docker-compose.yml` passes the following environment variables to the Work & Review Service:

- `USER_SERVICE_URL`
- `APPLICATION_SERVICE_URL`
- `PAYMENT_SERVICE_URL`

The payment URL wiring was added in commit `204fa14`. The configured internal service URLs must match the service names and ports used by the actual Compose configuration.

## 8. Automated Tests

The last recorded test run completed successfully:

`Ran 36 tests in 0.469s — OK`

Command used:

```powershell
docker compose exec work-review-service python manage.py test work_review --verbosity 2
```

The 36 tests cover the following areas. This inventory records the test cases and behaviors covered in the suite; use `work_review/tests.py` for the authoritative individual test names and assertions.

### 8.1 Review serializer validation

1. Reject a rating below 1.
2. Reject a rating above 5.
3. Reject self-review.
4. Accept valid basic review data.
5. Reject a duplicate review by the same reviewer for an assignment.
6. Detect a duplicate when the authenticated reviewer UUID and stored UUID are represented as strings.

### 8.2 Deliverable serializer validation

7. Reject editing a submitted deliverable.
8. Allow editing a draft deliverable.
9. Reject editing an approved deliverable.
10. Allow editing a deliverable requiring revisions.

### 8.3 Authentication and endpoint access

11. Reject unauthenticated work-list access.
12. Reject unauthenticated work creation.
13. Reject unauthenticated review-list access.
14. Reject unauthenticated review creation.
15. Return only the authenticated student's own work in the student work list.

### 8.4 Assignment client

The assignment-client tests use mocks rather than relying on a running external service. They cover client behavior for the configured URL/request, successful response handling, missing assignments, request/service failures, and unexpected or invalid responses. Check the test file for the exact number and names of these cases.

### 8.5 Payment client

The payment-client tests use mocks. They cover configuration/request behavior, successful responses, HTTP failures, request failures, invalid JSON or response formats, and invalid relative paths. Check the test file for the exact number and names of these cases.

### 8.6 Review endpoints

The review endpoint tests exercise the API with database-backed test records and include protection against a forged reviewer identity.

### 8.7 Work submission endpoints

The tests cover:

- Submission without a URL.
- Successful submission and timestamp/status update.
- A different student attempting to submit someone else's work.
- Attempting to submit work that is already submitted.
- Submission when the authenticated user ID is represented as a string.

### 8.8 Revision-request endpoints

The tests cover:

- A student attempting to request revisions receives HTTP 403.
- A nonexistent deliverable returns HTTP 404.
- A client receives HTTP 503 while ownership verification is unavailable.

### 8.9 Approval endpoints

The tests cover:

- A student attempting to approve work receives HTTP 403.
- A nonexistent deliverable returns HTTP 404.
- A client receives HTTP 503 while ownership verification is unavailable.

### 8.10 Work detail endpoints

The tests cover:

- A student cannot edit approved work.
- A different student cannot retrieve another student's work.

**Test-count note:** The suite has 36 passing tests in the last recorded run. The categories above summarize coverage; do not add the bullet points to calculate the test count because some client categories are grouped by behavior rather than enumerated test methods. Rerun the suite after any changes.

## 9. Commands for Development and Verification

Run these from the repository root in PowerShell.

### Check the current branch and working tree

```powershell
git status --short --branch
git branch --show-current
```

Expected branch:

`feature/work-review-service`

### Rebuild and start the service

```powershell
docker compose up -d --build work-review-service
```

Source files are not mounted into the container as live development volumes in the current setup. Rebuild the service after local Python code changes.

### Run Django system checks

```powershell
docker compose exec work-review-service python manage.py check
```

### Run the complete Work & Review test suite

```powershell
docker compose exec work-review-service python manage.py test work_review --verbosity 2
```

### Inspect service status and logs

```powershell
docker compose ps
docker compose logs --tail 100 work-review-service
```

### Inspect migration state

```powershell
docker compose exec work-review-service python manage.py showmigrations work_review
```

The initial migration `0001_initial.py` exists and had been applied during the previous work session.

## 10. Team Dependencies and Information Required

Do independent work first, then send one consolidated request to teammates if practical. Do not repeatedly message each teammate for every small detail.

### Person 1 — User & Authentication Service

Confirm:

- JWT signing algorithm.
- Exact shared secret environment-variable name and how it is supplied.
- Required JWT claims and user-ID claim name.
- Exact role values and capitalization.
- Token expiry and Bearer header format.
- A sample decoded payload with sensitive values omitted.

Then verify `work_review/authentication.py` against the real contract.

### Person 2 — Project Management Service

Only required if the assignment response does not expose enough ownership information:

- Endpoint to retrieve a project's client/owner.
- HTTP method and URL.
- Response fields and error behavior.
- Whether internal service authentication is required.

### Person 3 — Application & Assignment Service

Confirm:

- Whether `GET /api/assignments/{assignment_id}/` is the correct endpoint.
- A representative response object.
- Assignment ID, student ID, project ID, client/owner ID and status fields.
- Assignment status semantics and which statuses permit work submission/review.
- Authentication requirements for service-to-service calls.
- Missing-assignment and error response formats.

Use this information to implement ownership verification and assignment eligibility checks.

### Person 5 — Payment & Notification Service

Confirm:

- Payment request endpoint and HTTP method.
- Required JSON payload.
- How the amount is determined and which service is authoritative.
- Assignment/project identifiers required by the payment service.
- Success response and error response formats.
- Authentication requirements.
- Whether requests are idempotent and how duplicate payment requests are prevented.

Only then connect approval to a payment request. Approval must not set payment status to paid directly.

## 11. Remaining Work — Prioritized

### Priority 1: Complete service-to-service contracts

- [ ] Obtain and verify Person 1's JWT contract.
- [ ] Obtain Person 3's assignment endpoint and response schema.
- [ ] Determine how the client's ownership of an assignment/project is verified.
- [ ] Obtain Person 5's payment API contract.
- [ ] Obtain Person 2's owner lookup contract if assignment data does not contain the client ID.

These are the primary external blockers.

### Priority 2: Complete ownership and workflow validation

- [ ] Implement assignment lookup in the approval/revision workflow.
- [ ] Ensure only the owning client can approve or request revisions.
- [ ] Verify the assignment is in a state eligible for work submission/review.
- [ ] Confirm students can only create deliverables for assignments belonging to them.
- [ ] Confirm a deliverable's project ID matches its assignment's project ID.
- [ ] Confirm review participants belong to the relevant assignment.
- [ ] Decide and enforce when reviews are permitted, including whether completion is required.

### Priority 3: Finish payment integration

- [ ] Implement the approved payment request flow using Person 5's actual contract.
- [ ] Define what happens when payment service is unavailable.
- [ ] Prevent duplicate payment requests, including retries.
- [ ] Ensure approval and payment status remain separate.
- [ ] Add tests for payment request success, failure and duplicate/idempotency behavior.

### Priority 4: API and error consistency

- [ ] Compare implemented routes with `docs/api/API_CONTRACT.md`.
- [ ] Confirm the behavior of `/api/work/{work_id}/reject/`.
- [ ] Decide whether collection GET endpoints belong in the shared contract.
- [ ] Standardize error response bodies and status codes.
- [ ] Confirm authentication and role requirements for every endpoint.
- [ ] Add or update API documentation and examples.

### Priority 5: Expand automated tests

- [ ] Add tests for successful client approval after ownership verification is implemented.
- [ ] Add tests for successful revision requests and status transitions.
- [ ] Test wrong-client ownership attempts.
- [ ] Test assignment lookup success, missing assignment and service unavailability.
- [ ] Test assignment status restrictions.
- [ ] Test payment integration outcomes.
- [ ] Test review eligibility and participant validation.
- [ ] Rerun all 36 existing tests after changes and record the new count.
- [ ] Run the full project test suite once the other services are integrated.

### Priority 6: End-to-end integration

- [ ] Build and run all required services with Docker Compose.
- [ ] Verify gateway routing for all Work & Review endpoints.
- [ ] Test a complete workflow from login through work approval and review.
- [ ] Verify the payment service independently records payment state.
- [ ] Check logs and error behavior when a dependent service is unavailable.
- [ ] Update project diagrams or documentation if the final API contracts change.

## 12. Known Limitations at Handover

1. JWT compatibility with Person 1's implementation is not yet confirmed.
2. Assignment ownership and status validation are not complete.
3. Client approval and revision requests currently return HTTP 503 because ownership verification is unavailable.
4. The payment client exists, but payment requests are not integrated into approval.
5. The exact external API schemas are pending teammate confirmation.
6. Review eligibility rules need to be verified against the agreed project workflow.
7. The last recorded successful test run was 36 tests; rerun tests after subsequent edits.
8. A successful local test run does not establish that the complete multi-service workflow works end to end.

## 13. Git and Handover Status

The implementation commit has been pushed to:

`feature/work-review-service`

Commit:

`204fa14` — `Implement work review service foundation`

Branch URL:

https://github.com/AD-190206/campus-talent-connect/tree/feature/work-review-service

The branch was pushed with upstream tracking configured. The shared `main` branch was not modified by this branch-specific commit.

This context file is a separate handover/documentation change and should be committed and pushed to the same feature branch after reviewing it.

## 14. Recommended Next Session

1. Read this file and `docs/api/API_CONTRACT.md`.
2. Check `git status --short --branch`.
3. Run the Work & Review test suite to confirm the current baseline.
4. Collect the outstanding JWT, assignment and payment API contracts.
5. Implement ownership verification first, with tests.
6. Integrate payment only after the payment contract is confirmed.
7. Rerun tests and exercise the end-to-end workflow.
8. Update this file whenever the implementation state or blockers materially change.
