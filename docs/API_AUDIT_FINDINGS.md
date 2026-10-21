# Campus Talent Connect — API and Integration Audit Findings

**Status:** Audit findings and remediation tracker — inspected 2026-10-17  
**Purpose:** Track mismatches discovered before merging the service branches  
**Authoritative target:** `API_CONTRACT.md`

## 1. Audit scope and limitations

The audit inspected source files from the remote branches `origin/main`, `origin/feature/user-authentication`, `origin/person-2-project-service`, `origin/person3-application-service`, and `origin/person5-payment-service`, plus the current Work Review branch (`feature/work-review-service`). Gateway, Docker Compose, database initialization, environment examples, and the frontend on `origin/main` were also inspected.

No source files were changed during the audit. Findings below describe inspected code/configuration, not a fresh full test run. Where behaviour was inferred from visible code rather than confirmed by an end-to-end run, it is marked accordingly.

The frontend findings apply to the inspected `origin/main` snapshot; teammate feature branches had not been merged at the time of audit.

## 2. Executive summary

The repository has a useful common foundation: all five services are assigned ports 8001–8005, the gateway exposes port 8000, routes generally use `/api/`, the database initialization names align with Compose, and most services use UUIDs for their own resources. However, the current branches are **not ready for a seamless merge** without coordinated changes.

The most important blockers are:
1. User service currently uses integer user IDs, conflicting with the UUID contract and other services' UUID references.
2. Application service uses integer IDs for applications, assignments, and cross-service references, conflicting with Project and Work Review.
3. Authentication and authorization are incomplete/inconsistent, including endpoints that trust caller-supplied identities or expose unfiltered data.
4. Response envelopes are inconsistent across services.
5. Work Review ownership verification is unfinished, and the approval-to-payment workflow is not connected end-to-end.
6. Several endpoint and implementation bugs can cause runtime or serialization errors.
7. The frontend on `origin/main` is only a placeholder and does not make API calls.

## 3. Severity key

- **P0 — Merge/integration blocker:** identifier or security issue likely to break or invalidate core flows.
- **P1 — High priority:** functional, authorization, or contract issue that should be fixed before integration acceptance.
- **P2 — Medium priority:** consistency, reliability, or deployment issue that should be fixed before release.
- **P3 — Follow-up:** useful hardening or documentation improvement.

## 4. Findings by service/component

### 4.1 User & Authentication service

#### P0 — User IDs are integers, while the target contract requires UUIDs
**Evidence:** `User` has no explicit UUID primary key and uses Django's configured auto-incrementing `BigAutoField`; generated JWTs place `str(user.pk)` into `user_id`. Other services store user references as UUIDs.

**Impact:** JWT user IDs and references such as `student_id`, `client_id`, `payer_id`, and `reviewer_id` cannot be reliably joined/compared across services after the UUID target is adopted.

**Required action:** Plan and implement a coordinated UUID migration. Update model PKs, foreign keys/profile relationships, JWT claims, fixtures, test factories, API schemas, and any stored references. Do not change one service in isolation and assume existing IDs remain compatible.

#### P1 — User detail GET appears to have a missing return
**Evidence:** In the inspected `UserDetailView`, the GET method performs ownership checking but does not return the user payload; the intended response appears after the PUT method's return and is unreachable as part of GET.

**Impact:** `GET /api/users/{user_id}/` may return no valid response or fail at runtime.

**Required action:** Move the intended response into `get()` and add an API regression test for owner, admin, and forbidden access.

#### P1 — Refresh-token semantics are undefined
**Evidence:** `/api/auth/refresh/` requires JWT authentication and appears to issue another access token; a distinct refresh token and rotation flow were not demonstrated.

**Impact:** Clients cannot know the expected expiry/refresh behaviour, and the endpoint may not provide the security properties implied by its name.

**Required action:** Agree on a token policy, document it, and test expired/missing tokens and token renewal.

#### P1 — Development JWT secret fallback is unsafe
**Evidence:** JWT generation/validation uses a fallback such as `development-only-jwt-secret` if configuration is missing.

**Impact:** Misconfigured deployments could accept tokens signed with a known development secret.

**Required action:** Fail startup or reject authentication when the secret is missing outside development; use secure secret management.

#### P2 — User API responses do not yet match the mandatory common envelope
**Evidence:** Registration and login return top-level `message`, `user`, `access_token`, etc.; health/current-user responses are also not uniformly wrapped in `data`.

**Required action:** Wrap all successful responses in `data` and `message`, and standardize all error responses.

### 4.2 Project Management service

#### P0 — Real JWT authentication/authorization was not demonstrated
**Evidence:** The inspected settings did not show a configured DRF authentication class or global permission enforcement. Tests use `force_authenticate` with fake users, so they do not prove JWT validation works. PyJWT and a shared secret are present, and the README describes intended JWT behaviour, but the implementation was not established by the inspected files.

**Impact:** Protected project endpoints may not enforce the agreed identity and role rules.

**Required action:** Implement and test shared JWT authentication, explicit permissions, ownership checks, and invalid/expired-token behaviour. Confirm the implementation in source and with tests before marking complete.

#### P1 — Error and collection formats differ from the mandatory contract
**Evidence:** Some errors return `{"error": detail}` without a stable `code`/`details`; serializer errors may be returned directly. Project lists return `{"data": [...]}` but no pagination envelope was evident in the inspected view.

**Required action:** Adopt the common success/error envelopes and pagination rules for all endpoints.

#### P2 — Development configuration is permissive
**Evidence:** Debug defaults to enabled, allowed hosts are wildcarded, and CORS allows all origins in the inspected settings.

**Required action:** Keep permissive values only for local development; configure production-safe defaults and explicit allowed origins/hosts.

#### P2 — API tests bypass real authentication
**Evidence:** API tests use `force_authenticate` with fake users.

**Required action:** Retain unit-level permission tests but add integration tests using real signed JWTs and the same validation rules as other services.

### 4.3 Application & Assignment service

#### P0 — IDs and references are integers
**Evidence:** Application and Assignment use auto-increment IDs; `student_id`, `project_id`, and `application_id` are integer fields. Routes use `<int:pk>`. Project service uses UUID project IDs and Work Review expects UUID assignment/student/project references.

**Impact:** The services cannot exchange IDs consistently; requests may fail validation or compare incompatible types.

**Required action:** Migrate IDs and references to UUIDs, update route converters to UUIDs, serializers, database migrations, fixtures, tests, and service clients. Coordinate rollout with all dependent services.

#### P0 — Authentication/authorization is not enforced in inspected views
**Evidence:** Settings use `AllowAny` globally and do not show a shared JWT authentication class. Inspected views for create, list, detail, shortlist, select, reject, withdraw, and assignment detail did not show effective ownership/role enforcement.

**Impact:** A caller may submit applications using another student's ID, inspect other applications/assignments, or trigger status transitions without authorization.

**Required action:** Enforce JWT authentication and endpoint-specific role/ownership rules. Derive student identity from the token instead of trusting body/query identity.

#### P1 — Application rejection view is defined twice
**Evidence:** `ApplicationRejectView` appears twice; the later class definition shadows the earlier one.

**Impact:** The effective implementation may differ from the intended one and can conceal fixes/tests written for the first class.

**Required action:** Remove the duplicate and test the route against the single intended view.

#### P1 — Assignment list may serialize a queryset as a single object
**Evidence:** The project-filtered assignment path obtains a queryset but serializes it with `AssignmentSerializer(assignment).data` without `many=True`.

**Impact:** Multiple results can fail or produce incorrect response data.

**Required action:** Use collection serialization (`many=True`), add pagination, and test zero, one, and multiple assignment results.

#### P1 — Selection and assignment creation are not visibly atomic
**Evidence:** Service code sets an application to selected and then calls assignment creation without an encompassing transaction being demonstrated.

**Impact:** A failure during assignment creation can leave a selected application with no assignment.

**Required action:** Wrap status transition and assignment creation in one transaction; enforce uniqueness and valid status transitions at the service/database layer.

#### P1 — Status transition rules are inconsistent
**Evidence:** Serializer validation defines some allowed transitions, while service functions directly set statuses. The service layer does not consistently enforce transitions.

**Impact:** Alternate code paths can bypass lifecycle rules.

**Required action:** Centralize transition validation in the service layer and test every allowed/forbidden transition.

#### P2 — Response envelopes and security defaults are inconsistent
**Evidence:** Several endpoints return raw serialized objects/lists and flat errors; settings use a development secret fallback, `DEBUG` enabled by default, wildcard hosts, and permissive CORS.

**Required action:** Apply the mandatory common response contract and production-safe configuration.

### 4.4 Work & Review service

#### P0 — User ID type conflicts with the User service
**Evidence:** Work Review uses UUID fields for user and assignment references, while the inspected User service emits integer IDs converted to strings in JWTs.

**Impact:** Ownership comparisons and cross-service references can fail or silently refer to incompatible identities.

**Required action:** Coordinate the UUID migration and validate JWT `user_id` as a canonical UUID string.

#### P0 — Ownership verification is unfinished for revision/approval
**Evidence:** Revision and approval paths currently fail closed with `503 OWNERSHIP_VERIFICATION_UNAVAILABLE` where assignment ownership verification is not configured. Tests were designed to expect this temporary behaviour.

**Impact:** Core deliverable workflow cannot complete successfully for valid users.

**Required action:** Implement assignment lookup/participant verification and return the appropriate 401/403/404/502/503 contract errors. A temporary 503 is not acceptable as the final state.

#### P1 — Work creation does not fully verify assignment eligibility
**Evidence:** The create path stores the authenticated `user_id`, but full assignment/student/project validation was not demonstrated.

**Impact:** A user may create work against an assignment they do not own, or invalid references may be stored.

**Required action:** Verify assignment existence and that the authenticated user is the assigned student before creating deliverables.

#### P1 — Review eligibility checks are incomplete
**Evidence:** Review creation derives reviewer identity from JWT, but assignment participant eligibility checks were not demonstrated.

**Impact:** Reviews may be created by users who are not valid participants in the assignment.

**Required action:** Validate reviewer/reviewee participation, assignment status, rating range, and uniqueness before creation.

#### P1 — Internal assignment/payment calls do not carry explicit auth context
**Evidence:** Assignment client GET and Payment client POST did not attach an Authorization header or a demonstrated service credential. The current approval path does not complete payment integration.

**Impact:** A downstream service that correctly requires authentication may reject calls; alternatively, teams may weaken authentication to make the call work.

**Required action:** Define the internal-call security model and implement it explicitly. Do not disable auth as a workaround.

#### P2 — Downstream response validation and failure mapping need hardening
**Evidence:** Assignment client handles timeout/status cases but does not validate a shared response schema. Service-to-service failure semantics must align with the common envelope.

**Required action:** Validate response structure, use explicit timeouts, map upstream errors consistently, and test timeout, not-found, and malformed responses.

### 4.5 Payment & Notification service

#### P0 — Payment and notification data can be exposed across users
**Evidence:** Payment list starts with all payments and filters by `user_id` only if supplied. Payment detail fetches by ID without visible payer/payee ownership checks. Notification list starts with all notifications and filters by `user_id` only if supplied.

**Impact:** An authenticated user may be able to list or retrieve another user's payment or notification data.

**Required action:** Derive the caller identity from JWT and default all list/history/detail queries to the caller's authorized scope. Require explicit admin or trusted service permissions for broader access.

#### P0 — Payment creation trusts client-supplied identity fields
**Evidence:** `PaymentCreateSerializer` accepts `payer_id` and `payee_id`; visible view logic passes validated request data to the payment service without a demonstrated ownership/assignment authorization check.

**Impact:** Callers may attempt to create payments with forged payer/payee identities or invalid assignment relationships.

**Required action:** Derive or verify payer/payee and assignment from authenticated/trusted context. Validate assignment and amount against the authoritative workflow before creating payment records.

#### P1 — Notification creation can target arbitrary users
**Evidence:** Notification creation accepts `user_id`; no explicit trusted-sender/recipient authorization rule was demonstrated in the view.

**Impact:** A caller may create notifications for users they should not control.

**Required action:** Restrict notification creation to authorized trusted service actions or explicitly permitted senders, and validate recipients.

#### P1 — Work approval does not trigger payment release end-to-end
**Evidence:** Payment service has a release endpoint and Work Review has a Payment client, but the audited approval path does not invoke the complete payment-release workflow. The internal service URLs exist in Compose but their presence does not prove they are used.

**Impact:** Approval and payment state can diverge; users may not receive expected payments.

**Required action:** Agree on and implement a durable approval-to-payment workflow with retries/idempotency and clear state/error handling.

#### P1 — Payment processing is a mock, not a demonstrated provider integration
**Evidence:** Processing uses simulated success/failure and creates transaction IDs with a `MOCK-` prefix. No external provider credentials or live gateway integration were demonstrated in the service's `.env.example`.

**Impact:** The service must not be represented as a production payment gateway integration yet.

**Required action:** Explicitly label mock mode; define a provider adapter and test/sandbox credentials before claiming real gateway integration.

#### P1 — Release flow lacks demonstrated concurrency and authorization protection
**Evidence:** Release permits only `SUCCESS` status, but a transaction/row-locking strategy and caller ownership authorization were not demonstrated for the release function/view.

**Impact:** Concurrent release attempts and unauthorized calls may lead to inconsistent workflow outcomes.

**Required action:** Enforce authorized release, use atomic/locking semantics, make retries idempotent, and test concurrent calls.

#### P2 — Payment status exists without a demonstrated refund workflow
**Evidence:** `REFUNDED` is a model status, but a refund endpoint/function was not demonstrated in the audited route/service set.

**Impact:** Clients may assume refunds are supported when no complete workflow is available.

**Required action:** Either implement/document refunds or explicitly state they are not supported in this version.

#### P2 — Response formats and development settings need standardization
**Evidence:** Most success responses use `data` + `message`, but errors are flat and list endpoints lack pagination. Debug/host/CORS defaults are permissive.

**Required action:** Adopt the mandatory common envelopes, pagination, and production-safe settings.

### 4.6 Gateway, Compose, database initialization, and frontend

#### P1 — Gateway does not visibly enforce authentication
**Evidence:** Nginx routes path prefixes to services; no auth enforcement is shown in the inspected config.

**Impact:** This is not itself a defect if every backend validates tokens and permissions, but it makes backend enforcement essential. Gateway routing must not be mistaken for access control.

**Required action:** Enforce auth/authorization in services; confirm Authorization header forwarding in runtime tests. Add new route prefixes to Nginx when a new service path is introduced.

#### P1 — Health endpoints are not routed through the gateway
**Evidence:** The inspected gateway config routes auth/users/projects/applications/assignments/work/reviews/payments/notifications, but not a general `/api/health/` route.

**Impact:** A gateway-level health probe cannot reach service health endpoints through the current route map.

**Required action:** Decide whether health checks remain internal or are exposed through explicit service-specific gateway paths. Do not assume a single health path can unambiguously identify a service.

#### P2 — Compose uses service-start dependencies for integration
**Evidence:** Gateway and services use `depends_on` relationships based on service start; this does not necessarily mean an upstream service or database is ready to accept requests.

**Impact:** Startup races may cause transient failures.

**Required action:** Use health checks/healthy dependencies where supported and implement bounded retries for startup-dependent tasks.

#### P2 — Frontend is a placeholder in inspected `origin/main`
**Evidence:** `frontend/app/page.js` renders only a title, status text, and gateway URL. `frontend/next.config.js` enables `reactStrictMode` only; no API rewrites are configured.

**Impact:** There is no demonstrated frontend API integration or response-envelope handling in this snapshot.

**Required action:** Implement API client code using `NEXT_PUBLIC_API_BASE_URL`, parse the common success/error envelopes, and test authentication and error handling. These findings are specific to the inspected `origin/main` snapshot.

#### P2 — Environment templates differ by service
**Evidence:** Root `.env.example` defines shared URLs and settings, but the P5 service's own `.env.example` did not include the internal URLs observed in Compose.

**Impact:** Running a service outside Compose or with only its local template may omit configuration required for integration.

**Required action:** Align root and per-service environment documentation; document required versus optional values and safe defaults.

#### P3 — Development security defaults require production overrides
**Evidence:** Multiple Django services default to debug mode, wildcard hosts/CORS, and development secrets in local settings/templates.

**Required action:** Add explicit production configuration and startup validation; never deploy with sample secrets or permissive CORS/host settings.

## 5. Cross-cutting contract issues

### P0 — Mandatory response schema is not consistently implemented
Observed formats include:
- `{"data": ...}` without `message`;
- raw serialized objects or lists;
- `{"error": "..."}` without `code`;
- `{"error": "...", "code": "..."}` without `details`;
- direct serializer/framework error bodies.

**Required action:** Every service must implement the same success and error envelope, collection pagination, and stable status/code mapping from `API_CONTRACT.md`.

### P0 — UUID migration must be coordinated
User service and Application/Assignment service currently use integer IDs, while Project and Work Review use UUIDs and Payment expects UUID references. This cannot be solved safely by changing serializers alone. Migration sequencing, existing data, references, fixtures, and JWT claims must be coordinated.

### P1 — Authentication and authorization need end-to-end tests
Some services use JWT authentication; others did not demonstrate it in the inspected configuration. Even where JWT is configured, ownership checks are missing in several visible paths. Add tests for no token, malformed token, expired token, wrong role, non-owner access, admin access, and cross-service calls.

### P1 — Pagination is not standardized
No consistent page/page_size/pagination envelope was evident across all audited collection endpoints. All collection endpoints must implement the same contract.

### P1 — Error propagation between services is not standardized
A downstream timeout, authorization failure, malformed response, or not-found result must be distinguished. Use stable error codes and do not turn upstream outages into false 404s.

## 6. Recommended remediation order

1. **Freeze and approve the contract.** Resolve refresh-token policy, service-to-service identity, payment amount source, and approval/release workflow.
2. **Coordinate UUID migration.** Plan User IDs and Application/Assignment IDs with all dependent services before merging incompatible branches.
3. **Implement shared auth and authorization.** Use one JWT claim contract; enforce owner/role checks in every protected route.
4. **Fix correctness bugs.** User detail GET, duplicate reject view, assignment list serialization, status-transition enforcement, and atomic selection/assignment creation.
5. **Standardize response envelopes and pagination.** Update serializers/views/tests for all success and error paths.
6. **Complete Work Review assignment verification and payment workflow.** Include secure internal auth, retries, and idempotency.
7. **Enforce Payment/Notification data isolation.** Restrict list/detail/create/release operations to authorized identities.
8. **Integrate the frontend.** Use the configured gateway base URL and common envelope parser.
9. **Harden deployment configuration.** Secure secrets, disable debug in production, restrict hosts/CORS, and wait for dependencies to become healthy.
10. **Run integration acceptance tests.** Do not call integration complete until the contract checklist passes across all services through the gateway.

## 7. Merge readiness checklist

- [ ] Contract reviewed and approved by all service owners.
- [ ] UUID migrations agreed and tested against a copy of the integrated database.
- [ ] Every protected route validates JWT and enforces authorization.
- [ ] All success/error responses comply with the common schema.
- [ ] Every list route paginates consistently.
- [ ] All identified correctness bugs are fixed with regression tests.
- [ ] Cross-service clients use the correct URL, headers, timeout, and error mapping.
- [ ] Approval-to-payment workflow passes an end-to-end test.
- [ ] Payment and notification data are isolated by caller permissions.
- [ ] Frontend can register/login and call protected endpoints through the gateway.
- [ ] `docker compose up` plus migrations starts cleanly from a fresh local environment.
- [ ] Automated tests pass for each service and an integration smoke test passes through port 8000.

## 8. Audit caveat

This document is an inspection-based issue register. It does not assert that every listed defect has been reproduced in a running deployment, nor does it claim tests were rerun during the audit. Findings marked “not demonstrated” should be confirmed against the final merged code and covered by tests before closure.

## 9. Contract decisions now fixed by the project lead

The following choices are no longer open questions for implementation:
- 30-minute access JWTs and 7-day refresh JWTs; refresh rotation and logout revocation.
- Synchronous service-to-service requests forward the initiating user's bearer access token; every receiving service validates and authorizes independently.
- The published Project budget is the source of truth for gross payment amount.
- The first release uses a synchronous API workflow: payment is created/processed for the assignment, and Work Review approval calls Payment release.
- Common response envelopes and pagination are mandatory everywhere.
- UUIDs are mandatory for all public IDs and cross-service references.
- Mock payment processing may be used for development/testing only and must be clearly labelled.

These decisions are captured in `API_CONTRACT.md`. Implementation should begin against that contract. The contract is authoritative for coding, but integration is not complete until the acceptance checklist and audit remediation items pass.
