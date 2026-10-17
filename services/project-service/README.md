# project-service

**Owner:** Person 2

## Responsibility

Project creation, editing, closing, search, filtering and lifecycle.

## Rules

- Own this service's data.
- Do not directly query another service's database.
- Use REST for service-to-service communication.
- Use JWT claims for authenticated user identity/role.
- Use UUIDs/IDs for references to entities owned by other services.
- Keep endpoint changes synchronized with `docs/api/API_CONTRACT.md`.

## Local Docker endpoint

`http://localhost:8002`

Health endpoint:

`http://localhost:8002/api/health/`

## Response format

Success: `{"data": {...}, "message": "..."}`. Lists add
`"pagination": {"page", "page_size", "total", "total_pages"}`.

Error: `{"error": "...", "code": "...", "details": {}}`. Field errors are in
`details.fields`.

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Invalid body, field or query parameter |
| `INVALID_STATE_TRANSITION` | 400 | The project's status does not allow this action |
| `UNAUTHORIZED` | 401 | Missing, invalid, expired or non-access token |
| `FORBIDDEN` | 403 | Role or ownership not allowed |
| `NOT_FOUND` | 404 | Project missing or not visible to the caller |
| `INTERNAL_SERVER_ERROR` | 500 | Unexpected error (no details exposed) |

## Pagination

`GET /api/projects/?page=1&page_size=20`. Defaults 1 and 20, maximum
page_size 100. Invalid values return `400 VALIDATION_ERROR`.

## Statuses and transitions

| From | Allowed next status |
|---|---|
| `DRAFT` | `PUBLISHED`, `CLOSED` |
| `PUBLISHED` | `CLOSED` |
| `IN_PROGRESS` | `CLOSED` |
| `COMPLETED`, `CLOSED`, `ARCHIVED` | none |

`IN_PROGRESS`, `COMPLETED` and `ARCHIVED` are reserved: no endpoint sets them
in this iteration. Projects can be edited only in `DRAFT` or `PUBLISHED`, and
deleted only in `DRAFT`, `CLOSED` or `ARCHIVED`.

## Who can do what

- Students: read published projects (lists), read any non-draft project by ID.
- Clients: create projects; edit, publish, close and delete their own.
- Admins: read everything; close and delete any project.
- Someone else's draft returns 404.
- Identity and role come only from the JWT (HS256, `token_type=access`,
  `user_id` UUID, `role` STUDENT/CLIENT/ADMIN). Request bodies containing
  `client_id`, `status` or unknown fields are rejected.

## Extra environment variables

`DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`. With `DJANGO_DEBUG` off the
service will not start unless `DJANGO_SECRET_KEY` and `JWT_SECRET_KEY` are real
values.