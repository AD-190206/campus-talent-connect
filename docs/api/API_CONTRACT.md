# Campus Talent Connect — Authoritative API Contract

**Status:** Team implementation baseline — decisions made by project lead on 2026-10-17  
**Scope:** User & Authentication, Project Management, Application & Assignment, Work & Review, Payment & Notification, API Gateway, and frontend  
**Route prefix:** `/api/`  
**Purpose:** Establish one mandatory API contract for all services before branch integration.

> This document is the authoritative implementation target for the current integration. Existing branches do not yet fully comply. See `API_AUDIT_FINDINGS.md` for the required remediation work. Contributors should implement this contract rather than preserve incompatible current behaviour.

## 1. Normative language

The terms **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are requirements, not suggestions.

- **MUST / MUST NOT:** required for integration acceptance.
- **SHOULD / SHOULD NOT:** recommended unless the team documents an approved exception.
- **MAY:** optional.

## 2. Services and ownership

| Service | Container/service name | Port | Owns |
|---|---|---:|---|
| User & Authentication | `user-service` | 8001 | Accounts, credentials, roles, student/client profiles, token issuance |
| Project Management | `project-service` | 8002 | Projects, project lifecycle, search/filtering |
| Application & Assignment | `application-service` | 8003 | Applications, application lifecycle, assignments |
| Work & Review | `work-review-service` | 8004 | Deliverables, submission/revision/approval, reviews and ratings |
| Payment & Notification | `payment-notification-service` | 8005 | Payments, payment lifecycle, notifications |
| API Gateway | `gateway` | 8000 host-facing | Routes browser/API traffic to service owners |

Each service MUST own and mutate only its own data. A service MUST NOT read or write another service's database directly. Cross-service access MUST use documented HTTP APIs.

The five databases remain separate logical databases on PostgreSQL:
`ctc_users`, `ctc_projects`, `ctc_applications`, `ctc_work_reviews`, and `ctc_payments`.

## 3. Base URL and routing

- Browser-facing base URL in local development: `http://localhost:8000/api`
- All service routes MUST use the existing `/api/` prefix. Do not introduce `/api/v1/` as part of this integration.
- Internal Docker calls MUST use service DNS names and ports, e.g. `http://application-service:8003`.
- Trailing-slash behaviour MUST be consistent with the route definitions below. Clients SHOULD use the trailing slash shown in the route definitions.
- The gateway MUST route each documented path to its owning service and MUST preserve the request method, body, query string, and `Authorization` header.
- Service health checks MAY be internal; if exposed publicly, they MUST be explicitly documented and MUST NOT reveal secrets.

## 4. Common HTTP and data rules

- Request and response bodies MUST use JSON, except where a specific upload format is separately documented.
- Services MUST use UTF-8 JSON and the correct `Content-Type: application/json` header for JSON bodies.
- IDs and cross-service entity references MUST be UUIDs represented as canonical UUID strings. Integer IDs MUST NOT be used in public API payloads or inter-service contracts.
- Timestamps MUST be ISO 8601 strings with an explicit timezone. APIs SHOULD return UTC timestamps ending in `Z`.
- Dates without a time, such as a project deadline, MUST use `YYYY-MM-DD`.
- Monetary values MUST be decimal strings in JSON (for example `"1250.00"`) to avoid floating-point ambiguity. Amounts MUST be positive where a payment is created; fee MUST be non-negative.
- Enum values are case-sensitive and MUST match the values documented by the owning service.
- Services MUST validate request bodies and return a structured 4xx response for invalid input; they MUST NOT expose stack traces, secrets, database credentials, or internal exception details.
- Unknown fields SHOULD be rejected for mutation requests unless the endpoint explicitly permits them.

## 5. Authentication and authorization

### 5.1 Bearer token

Protected endpoints MUST require:
`Authorization: Bearer <access_token>`

The User & Authentication service issues access tokens. All other services MUST validate tokens locally using the shared configured signing secret and the agreed algorithm; they MUST NOT query the User service's database just to authenticate a request.

### 5.2 JWT claims

The target access-token claims are:

| Claim | Requirement |
|---|---|
| `user_id` | REQUIRED on user access and refresh tokens; canonical UUID string |
| `role` | REQUIRED on user access and refresh tokens; one of `STUDENT`, `CLIENT`, `ADMIN` |
| `iat` | REQUIRED; issued-at Unix timestamp |
| `exp` | REQUIRED; expiration Unix timestamp |
| `token_type` | REQUIRED; `access` or `refresh` |

- The signing algorithm MUST be explicitly pinned to `HS256` for the current shared-secret implementation; services MUST reject tokens using another algorithm.
- `POST /api/auth/refresh/` MUST accept a refresh token and return a new access token plus a rotated refresh token, both inside the common success envelope.
- `POST /api/auth/logout/` MUST revoke the supplied refresh token and return a common success envelope. The User service MUST add this endpoint.
- Missing, malformed, expired, or invalid-signature tokens MUST receive `401 UNAUTHORIZED`.
- Missing or invalid role claims MUST be rejected on protected endpoints.
- The development fallback JWT secret MUST NOT be used in production. Production secrets MUST be provided through environment/secret management and MUST not be committed.
- The current User service uses integer database primary keys. Before this contract can be considered implemented, its IDs and related references MUST be migrated to UUIDs, and all services MUST agree on the migration and rollout plan.

### 5.3 Authorization

Authentication is not authorization. Every protected operation MUST enforce role, ownership, and resource-state rules at the owning service.

- A service MUST derive the acting user identity from the validated JWT, not trust a client-supplied `student_id`, `client_id`, `payer_id`, `reviewer_id`, or equivalent identity field.
- A caller MUST NOT access another user's private resource merely by supplying its UUID.
- Administrative access MUST be explicitly checked.
- For this integration, synchronous service-to-service calls MUST forward the original user's `Authorization` bearer access token when the call is part of that user's request. The receiving service MUST validate it and independently authorize the operation.
- This initial integration MUST NOT use an unauthenticated service-to-service bypass or invent a separate service-token scheme. Background/system actions requiring no user context are out of scope until a dedicated service-identity contract is approved.
- Internal endpoints MUST NOT be made public solely to make service integration easier.

## 6. Mandatory response envelopes

**Every service endpoint, including success, error, list, and mutation responses, MUST follow these envelopes.** The only exceptions are bodyless `204 No Content` responses, which are discouraged for this contract; prefer a JSON success envelope instead.

### 6.1 Success

Single resource or operation:
```json
{
  "data": {
    "id": "7b8a9b8a-9f4b-4cb8-a0a6-0c2a0a8c20c1"
  },
  "message": "Operation successful"
}
```

Collection:
```json
{
  "data": [],
  "message": "Resources retrieved successfully",
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 0,
    "total_pages": 0
  }
}
```

Rules:
- `data` MUST always be present on a success response. It MUST be an object for a single resource/operation and an array for a collection.
- `message` MUST always be a non-empty human-readable string.
- Collection endpoints MUST include `pagination`.
- Collection endpoints MUST accept `page` and `page_size`; defaults are `page=1`, `page_size=20`; maximum `page_size=100`. Invalid values MUST return `400 VALIDATION_ERROR`.
- `total` is the total number of matching resources before pagination; `total_pages` is `0` when total is zero, otherwise the ceiling of `total / page_size`.
- Successful creates MUST return HTTP `201 Created`. Reads and successful updates/actions MUST return an appropriate `200 OK`. A delete/action SHOULD return a JSON envelope rather than a bodyless response.

### 6.2 Error

Every error response MUST use:
```json
{
  "error": "Human-readable error message",
  "code": "ERROR_CODE",
  "details": {}
}
```

- `error` MUST be a non-empty string.
- `code` MUST be a stable machine-readable uppercase code.
- `details` MUST always be present; use `{}` when no field-level details exist.
- Validation errors SHOULD use `details.fields` to map field names to messages.
- The envelope MUST NOT contain stack traces or secrets.
- Services MUST NOT return raw Django REST Framework serializer errors or framework-generated error bodies directly; they MUST translate them into this envelope.

### 6.3 Required status mapping

| HTTP status | Meaning | Example code |
|---:|---|---|
| 400 | Invalid request or invalid state transition | `VALIDATION_ERROR` / `INVALID_STATE_TRANSITION` |
| 401 | Missing/invalid/expired authentication | `UNAUTHORIZED` |
| 403 | Authenticated but not permitted | `FORBIDDEN` |
| 404 | Resource does not exist or caller is not allowed to discover it, according to the service's disclosure policy | `NOT_FOUND` |
| 409 | Duplicate, idempotency conflict, or incompatible current state | `CONFLICT` / `DUPLICATE_APPLICATION` / `IDEMPOTENCY_KEY_CONFLICT` |
| 422 | Optional alternative for semantically invalid input, only if used consistently across all services | `UNPROCESSABLE_ENTITY` |
| 429 | Rate limit exceeded | `RATE_LIMITED` |
| 500 | Unexpected server error | `INTERNAL_SERVER_ERROR` |
| 502/503/504 | Upstream service/gateway failure or timeout | `UPSTREAM_SERVICE_ERROR` |

For integration simplicity, the team SHOULD prefer `400` for validation and invalid state transitions and `409` for conflicts, rather than mixing `400` and `422` arbitrarily.

## 7. Common endpoint conventions

- Query parameters MUST be documented and validated by the owning service.
- List endpoints MUST paginate and use the collection envelope.
- Resource detail endpoints MUST return the single-resource envelope.
- All endpoint error paths MUST use the common error envelope.
- `health/` MAY use a small service health payload, but for strict envelope compliance it SHOULD return `{"data":{"service":"...","status":"healthy"},"message":"Health check successful"}`.
- APIs MUST document which roles may invoke each endpoint and which identity/resource ownership checks apply.
- Duplicate create operations SHOULD be protected by database constraints and, where appropriate, idempotency keys.

## 8. Endpoint catalogue

The following is the target endpoint catalogue based on the existing contract and audited routes. Exact request/response schemas and transition rules must be implemented and tested against this document.

### 8.1 User & Authentication — `user-service:8001`

| Method | Route | Access | Purpose |
|---|---|---|---|
| POST | `/api/auth/register/` | Public | Register a student or client |
| POST | `/api/auth/login/` | Public | Authenticate and issue access token |
| POST | `/api/auth/refresh/` | Valid refresh token | Rotate refresh token and issue new access token |
| POST | `/api/auth/logout/` | Valid refresh token | Revoke refresh token |
| GET | `/api/auth/me/` | Authenticated | Return current user's identity |
| GET | `/api/users/{user_id}/` | Owner or admin | Get user details |
| PUT/PATCH | `/api/users/{user_id}/` | Owner or admin | Update allowed user fields |
| GET | `/api/users/{user_id}/profile/` | Owner or admin | Get student/client profile |
| PUT/PATCH | `/api/users/{user_id}/profile/` | Owner or admin | Update profile |
| POST | `/api/users/{user_id}/deactivate/` | Owner or admin | Deactivate account |

Contract requirements:
- Registration MUST return a UUID `user_id`; passwords MUST never be returned.
- Login MUST return `access_token`, `token_type: "Bearer"`, `expires_in`, and a user object, inside the `data` envelope.
- Refresh-token policy is fixed for this contract: 30-minute access tokens, 7-day refresh tokens, rotation on refresh, and revocation on logout. The current implementation must be updated to support this policy.
- User detail GET MUST be implemented and tested; the audited branch has an apparent missing return in the view.
- The `ADMIN` role MUST not be self-assignable through public registration.

### 8.2 Project Management — `project-service:8002`

| Method | Route | Access | Purpose |
|---|---|---|---|
| GET | `/api/projects/` | Authenticated | List/search/filter visible projects |
| POST | `/api/projects/` | Client | Create project |
| GET | `/api/projects/{project_id}/` | Authenticated, visibility rules apply | Get project |
| PUT/PATCH | `/api/projects/{project_id}/` | Owning client or admin according to policy | Update project |
| DELETE | `/api/projects/{project_id}/` | Owner or admin | Delete project, subject to lifecycle policy |
| POST | `/api/projects/{project_id}/publish/` | Owning client | Publish draft project |
| POST | `/api/projects/{project_id}/close/` | Owning client or admin according to policy | Close project |
| GET | `/api/projects/{project_id}/status/` | Owner/admin and any explicitly authorized participant | Get lifecycle status |

Known query parameters from the audited branch: `query`, `skill`, `category`, `max_budget`, plus mandatory pagination parameters `page`, `page_size`.

Project status values currently observed in the model: `DRAFT`, `PUBLISHED`, `IN_PROGRESS`, `COMPLETED`, `CLOSED`, `ARCHIVED`. The team MUST standardize case and lifecycle transitions in API docs and tests before implementation.

### 8.3 Application & Assignment — `application-service:8003`

| Method | Route | Access | Purpose |
|---|---|---|---|
| GET | `/api/applications/` | Owning client for project applications; student for own applications; admin | List applications, filtered by `project_id` or `student_id` |
| POST | `/api/applications/` | Student | Apply to project |
| GET | `/api/applications/{application_id}/` | Applicant, owning client, or admin | Get application |
| PUT/PATCH | `/api/applications/{application_id}/` | Applicant, while editable | Update proposal/resume |
| POST | `/api/applications/{application_id}/shortlist/` | Owning client | Shortlist application |
| POST | `/api/applications/{application_id}/select/` | Owning client | Select applicant and create assignment atomically |
| POST | `/api/applications/{application_id}/reject/` | Owning client | Reject application |
| POST | `/api/applications/{application_id}/withdraw/` | Applicant, while withdrawable | Withdraw application |
| GET | `/api/assignments/` | Assignment participants or admin; client project-owner rules apply | List assignments, optionally filtered by project |
| GET | `/api/assignments/{assignment_id}/` | Assignment participants or admin | Get assignment |

Requirements:
- Application and Assignment IDs, plus `student_id`, `project_id`, and `application_id` references, MUST be UUIDs.
- The student ID MUST be derived from the authenticated token; request body identity fields MUST NOT override it.
- The project service MUST be consulted or an agreed trusted project context used to validate that a project exists and is eligible for applications.
- Database uniqueness MUST prevent duplicate applications for `(student_id, project_id)`.
- Application status transitions MUST be enforced in service logic and atomically persisted.
- Selecting an applicant and creating an assignment MUST be one atomic transaction.
- Assignment list serialization MUST return an array for collection results, never a single-object serializer applied to a queryset.

Application statuses observed in the audited branch: `submitted`, `shortlisted`, `selected`, `rejected`, `withdrawn`. Assignment statuses observed: `active`, `completed`, `cancelled`. These values MUST be kept consistent across services.

### 8.4 Work & Review — `work-review-service:8004`

| Method | Route | Access | Purpose |
|---|---|---|---|
| GET | `/api/work/` | Assignment participants or admin; filtering rules to be finalized | List work/deliverables |
| POST | `/api/work/` | Assigned student | Create deliverable/draft |
| GET | `/api/work/{work_id}/` | Assignment participants or admin | Get deliverable |
| PUT/PATCH | `/api/work/{work_id}/` | Assigned student while editable | Update draft/submission fields allowed by policy |
| POST | `/api/work/{work_id}/submit/` | Assigned student | Submit deliverable |
| POST | `/api/work/{work_id}/reject/` | Owning client | Request revision with feedback |
| POST | `/api/work/{work_id}/approve/` | Owning client | Approve deliverable and initiate agreed completion/payment workflow |
| POST | `/api/reviews/` | Eligible assignment participant | Submit a review |
| GET | `/api/reviews/{review_id}/` | Review participants or admin | Get review |

Requirements:
- Work, Review, assignment, student, project, reviewer, and reviewee identifiers MUST be UUIDs.
- Work creation MUST verify that the assignment exists and the authenticated user is its assigned student.
- Revision and approval MUST verify assignment ownership/participant eligibility. Temporary `503 OWNERSHIP_VERIFICATION_UNAVAILABLE` behaviour is not an acceptable final integration state.
- Reviews MUST verify that the reviewer and reviewee are eligible participants of the referenced assignment, and enforce the one-review-per-assignment/reviewer uniqueness rule.
- Rating MUST be an integer from 1 through 5.
- The team MUST agree on whether approval triggers payment release directly or through an asynchronous event/workflow. The current branches do not yet demonstrate a complete connected flow.

Deliverable statuses observed in the audited branch: `DRAFT`, `SUBMITTED`, `REVISION_REQUESTED`, `APPROVED`.

### 8.5 Payment & Notification — `payment-notification-service:8005`

| Method | Route | Access | Purpose |
|---|---|---|---|
| GET | `/api/payments/` | Authenticated; return only caller-authorized payments | List/filter payments |
| POST | `/api/payments/` | Trusted workflow or authorized client according to agreed payment model | Create payment intent/record |
| GET | `/api/payments/history/` | Authenticated; caller's own history | List caller's payment history |
| GET | `/api/payments/{payment_id}/` | Payer, payee, or admin | Get payment |
| POST | `/api/payments/{payment_id}/process/` | Trusted payment workflow or authorized system action | Process payment |
| POST | `/api/payments/{payment_id}/release/` | Authorized completion workflow | Release eligible successful payment |
| GET | `/api/notifications/` | Authenticated; caller's own notifications | List notifications, optionally unread-filtered |
| POST | `/api/notifications/` | Trusted service/system or explicitly authorized sender | Create notification |

Requirements:
- Payment and Notification IDs, assignment/payer/payee/user IDs MUST be UUIDs.
- The service MUST derive payer identity from authenticated context unless the request is a trusted service-to-service action with a documented authorization mechanism.
- Payment creation MUST validate assignment, payer, payee, amount, and authorization with the relevant services or trusted workflow context.
- Payment listing/history and detail MUST enforce payer/payee ownership; omitting `user_id` MUST NOT reveal every user's payments.
- Notification listing MUST return only the current user's notifications unless a privileged role or trusted internal scope is explicitly authorized.
- Notification creation MUST prevent arbitrary callers from creating notifications for arbitrary users.
- Idempotency MUST be supported for payment creation; reusing a key with different immutable request details MUST return `409 IDEMPOTENCY_KEY_CONFLICT`.
- Real payment provider integration versus mock processing MUST be explicitly identified by environment and never misrepresented.
- A payment MUST NOT be released before the agreed completion/approval conditions are met.

Payment statuses observed in the audited branch: `PENDING`, `PROCESSING`, `SUCCESS`, `FAILED`, `REFUNDED`, `RELEASED`. Notification types observed: `IN_APP`, `EMAIL`, `SMS`.

## 9. Cross-service workflows

### 9.1 Apply and select

1. Student authenticates with User service and receives a JWT containing UUID `user_id` and role.
2. Student submits an application through Application service. The service derives student identity from JWT and validates project eligibility.
3. Owning client reviews applications and selects one.
4. Application service enforces valid status transition and creates the assignment in the same transaction.
5. Assignment UUID is returned and becomes the shared reference for Work Review and Payment.

### 9.2 Deliverable approval and payment

The required initial workflow is synchronous and API-based:

1. The selected application creates an assignment atomically.
2. The owning client creates a payment for that assignment. The **Project service's published project budget** is the source of truth for the gross amount; the payment service MUST retrieve/verify the project/assignment context and MUST NOT trust an arbitrary client-supplied amount.
3. The payment service records the payment and processes it. In the current project iteration, processing may use the existing mock provider, but responses and state transitions MUST clearly identify mock mode.
4. The assigned student creates and submits work. Work Review verifies assignment and student ownership.
5. The owning client requests revision or approves the deliverable.
6. On approval, Work Review MUST call Payment service `POST /api/payments/{payment_id}/release/`, forwarding the client's bearer access token. Payment service MUST verify the payment, assignment, project owner, status, and release eligibility before release.
7. Payment and notification state changes MUST be idempotent. Repeated approval/release requests MUST NOT release funds or create duplicate effects more than once.
8. Notifications are created by the Payment service for the payer and payee on relevant payment lifecycle events. Work Review may create other notifications only through an explicitly authorized notification operation.

The first implementation MUST use this synchronous API workflow. A durable asynchronous/event-driven workflow may be introduced later only as a separately reviewed contract change. The current audit did not find a complete approval-to-payment-release connection, so implementing and testing it is a merge blocker.

## 10. Internal service calls and failure behaviour

- Internal service base URLs MUST be supplied through environment variables; no hard-coded localhost URLs for container-to-container calls.
- Calls MUST have explicit connect/read timeouts and handle non-2xx responses.
- An unavailable dependency MUST produce a stable `502` or `503` error envelope with a stable code; it MUST NOT be mistaken for “resource does not exist”.
- A service MUST NOT report a cross-service action as successful until its own durable action succeeds and the workflow's success criteria are met.
- Retryable operations MUST be idempotent or use idempotency keys.
- Services MUST pass the caller's Authorization header only when acting on behalf of that caller; trusted service actions need an explicit service-identity policy.

## 11. Environment and deployment configuration

The current root `.env.example` defines these names:
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
- `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `JWT_SECRET_KEY`
- `USER_DB_NAME`, `PROJECT_DB_NAME`, `APPLICATION_DB_NAME`, `WORK_REVIEW_DB_NAME`, `PAYMENT_DB_NAME`
- `USER_SERVICE_URL`, `PROJECT_SERVICE_URL`, `APPLICATION_SERVICE_URL`, `WORK_REVIEW_SERVICE_URL`, `PAYMENT_NOTIFICATION_SERVICE_URL`
- `NEXT_PUBLIC_API_BASE_URL`

The current frontend value is `http://localhost:8000/api`. Frontend code must use this configured base URL; browser-facing API calls must not use Docker-only service hostnames.

- Development defaults MUST NOT be used in production.
- `DEBUG` MUST be disabled in production, allowed hosts must be explicit, and CORS must be restricted to approved origins.
- Secrets MUST be supplied securely and MUST NOT be committed.
- Container health/dependency checks SHOULD wait for service readiness, not merely process start.

## 12. Contract acceptance checklist

A branch is ready to merge into the integration branch only when all applicable items pass:

- [ ] All public entity IDs and cross-service references use UUIDs.
- [ ] All protected endpoints validate the common JWT contract.
- [ ] All endpoints enforce role, ownership, and lifecycle rules.
- [ ] All successful responses use the mandatory `data` + `message` envelope.
- [ ] All collection responses include `pagination`.
- [ ] All error responses use `error`, `code`, and `details`.
- [ ] No endpoint returns raw serializer/framework errors.
- [ ] API paths use the `/api/` prefix and are routed by the gateway.
- [ ] Cross-service calls use configured URLs, timeouts, and stable error handling.
- [ ] Application selection and assignment creation are atomic.
- [ ] Work creation/revision/approval and review eligibility are verified against assignments.
- [ ] Payment and notification access is isolated to authorized users.
- [ ] Approval-to-payment workflow is implemented, idempotent, and tested.
- [ ] Automated tests cover success, validation, unauthenticated, forbidden, not-found, conflict, upstream failure, and pagination cases.
- [ ] Compose configuration, environment examples, migrations, README files, and API docs agree.
- [ ] Frontend uses the configured gateway base URL and handles the common envelopes.

## 13. Decisions fixed for this integration

These decisions are authoritative for the current implementation and should not be reopened in individual service branches. A change requires an explicit contract revision approved by the project lead.

1. **API prefix:** `/api/`; no `/api/v1/` prefix.
2. **Identifiers:** UUIDs for every public ID and cross-service reference, including User, Application, Assignment, Work, Review, Project, Payment, and Notification.
3. **Response schema:** mandatory success envelope (`data`, `message`), mandatory error envelope (`error`, `code`, `details`), and pagination on every collection endpoint.
4. **JWT:** HS256; access token lifetime 30 minutes; refresh token lifetime 7 days; refresh rotation and logout revocation; `user_id` UUID string; `role` and `token_type` required.
5. **Internal calls:** forward the initiating user's bearer access token for synchronous user-driven service calls; receiving services validate and authorize independently. No unauthenticated internal bypass.
6. **Pagination:** `page=1`, `page_size=20`, maximum `page_size=100`; response includes `page`, `page_size`, `total`, and `total_pages`.
7. **Payment amount:** the published project budget is the gross amount source of truth. The service must validate assignment/project context and must not trust a caller-supplied amount alone. Fee calculation must be explicit in the Payment service and documented in its response.
8. **Payment workflow:** synchronous API calls for this iteration; client creates/processes the payment for the assignment, and Work Review approval calls the Payment release endpoint. Release must be authorized and idempotent.
9. **Payment provider:** mock processing is acceptable only for development/testing and must be clearly identified. It must not be represented as a live payment gateway.
10. **Lifecycle transitions:** owning service enforces transitions in its service layer and tests them. Existing status values may be retained where documented, but invalid transitions are rejected consistently.
11. **Database access:** each service accesses only its own database; cross-service data comes through APIs.
12. **Production security:** no development secret fallback in production; debug off; explicit hosts/CORS; secrets are not committed.

The migration must be coordinated across services. No service should be treated as integration-ready while its IDs, authentication, responses, or workflow violate these decisions.

## 14. Revision 1 — integration additions (2026-10-21)

These additions were needed to run the §9 workflow end to end. They extend the catalogue without changing any existing route, envelope or decision in §13. `scripts/e2e_test.py` exercises all of them.

### 14.1 Project lifecycle (Project service)

| Method | Route | Access | Purpose |
|---|---|---|---|
| POST | `/api/projects/{project_id}/start/` | Owning client | `PUBLISHED` → `IN_PROGRESS`. Called by the Application service when an applicant is selected (client token forwarded). Idempotent. |
| POST | `/api/projects/{project_id}/complete/` | Owning client | `IN_PROGRESS` → `COMPLETED`. Called by Work & Review on approval. Idempotent. |

Allowed transitions: `DRAFT → PUBLISHED | CLOSED`, `PUBLISHED → IN_PROGRESS | CLOSED`, `IN_PROGRESS → COMPLETED | CLOSED`. `ARCHIVED` is reserved. Projects can be edited only while `DRAFT` or `PUBLISHED`, so the budget is frozen once work starts.

### 14.2 Applications and assignments (Application service)

| Method | Route | Access | Purpose |
|---|---|---|---|
| POST | `/api/assignments/{assignment_id}/complete/` | Assignment's client | `active` → `completed`, sets `completion_date`. Called by Work & Review on approval. Idempotent. |

- `GET /api/applications/`: students see only their own applications; clients must pass `project_id` for a project they own; admins may filter freely. Optional `status` filter.
- `POST /api/applications/` accepts only `project_id`, `proposal`, `resume_url`; any other field (including `student_id`) is a `400 VALIDATION_ERROR`.
- Application transitions: `submitted → shortlisted | rejected | withdrawn`, `shortlisted → selected | rejected | withdrawn`. Proposals are editable only while `submitted`.
- A project has exactly one assignment (database constraint). Selecting an applicant, in one transaction: marks it `selected`, creates the assignment, rejects the project's other open applications and starts the project. If starting the project fails, everything rolls back.
- `GET /api/assignments/` returns only assignments where the caller is the student or client (admins see all). Optional `project_id` and `status` filters.

### 14.3 Work & Review

- `GET /api/work/`: students see their own deliverables; clients must pass `assignment_id` for an assignment they own; admins see all. Optional `assignment_id` and `status` filters. Clients may also `GET /api/work/{work_id}/` for their assignments; only the student may edit.
- Work can only be created for an `active` assignment.
- `POST /api/work/{work_id}/approve/`:
  1. reuses the client's active payment for the assignment (`GET /api/payments/?assignment_id=`) or creates one with idempotency key `work-review-assignment-{assignment_id}`;
  2. processes it if still `PENDING`/`PROCESSING`, then releases it;
  3. completes the project and the assignment;
  4. only then marks the work `APPROVED`.

  Every step is idempotent, so a failed approval (for example `503 UPSTREAM_SERVICE_ERROR`) can be retried safely. The response includes `data.payment` (`id`, `status`).
- `POST /api/reviews/` requires the assignment to be `completed`. `GET /api/reviews/` lists reviews the caller wrote or received (optional `assignment_id` filter).

### 14.4 Payments and notifications

- `GET /api/payments/` and `/api/payments/history/` accept optional `assignment_id` and `status` filters (results are always limited to the caller's payments).
- At most one active payment (any status other than `FAILED`/`REFUNDED`) per assignment. A second one returns `409 CONFLICT` with `details.payment_id`.
- `amount` in the request body is ignored; the amount is always the project budget.
- Payment responses include `fee` (currently always `0.00`), `net_amount` (`amount - fee`) and `payment_mode` (`"MOCK"`).
- Release eligibility: the payment must be `SUCCESS`, the caller must be the payer who owns the project, the payee must be the assigned student, **and** the assignment must have at least one `SUBMITTED` or `APPROVED` deliverable (checked with Work & Review). Otherwise `409 PAYMENT_RELEASE_NOT_ALLOWED`.
- Releasing creates `PAYMENT_RELEASED` notifications for the payee and payer.
- Processing while no provider is configured returns `503 PAYMENT_PROVIDER_UNAVAILABLE`. Set `MOCK_PAYMENT_ENABLED=1` (the default in `.env.example`) for development.

### 14.5 Platform-wide

- All services return UTC timestamps ending in `Z`.
- Unknown routes and unreachable services return the error envelope (`NOT_FOUND`, `UPSTREAM_SERVICE_ERROR`) from both the services and the gateway. The gateway accepts collection roots without the trailing slash (`/api/projects` is served as `/api/projects/`); deeper routes must use the trailing slash shown in §8.
- Upstream failures from service-to-service calls use `502`/`503`/`504` with `UPSTREAM_SERVICE_ERROR` (or the more specific `UPSTREAM_*` codes in the Payment service).
