# CTC API Contract

This document is the shared contract between the frontend and the five backend teams.

## General rules

- Base URL from the browser: `/api`
- Authentication: `Authorization: Bearer <JWT>`
- JSON request/response bodies
- IDs should be UUIDs
- Services must not directly access another service's database
- Service-to-service communication uses REST

## Standard response conventions

### Success

```json
{
  "data": {},
  "message": "Operation successful"
}
```

### Error

```json
{
  "error": "Human-readable error message",
  "code": "ERROR_CODE"
}
```

## Endpoint ownership

### User & Authentication

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh

GET  /api/users/{user_id}
PUT  /api/users/{user_id}
GET  /api/users/{user_id}/profile
PUT  /api/users/{user_id}/profile
```

### Project Management

```text
POST   /api/projects/
GET    /api/projects/
GET    /api/projects/{project_id}/
PUT    /api/projects/{project_id}/
DELETE /api/projects/{project_id}/
POST   /api/projects/{project_id}/close/
GET    /api/projects/{project_id}/status/
```

### Application & Assignment

```text
POST /api/applications/
GET  /api/applications/
GET  /api/applications/{application_id}/
PUT  /api/applications/{application_id}/

POST /api/applications/{application_id}/shortlist/
POST /api/applications/{application_id}/select/

POST /api/assignments/
GET  /api/assignments/{assignment_id}/
```

### Work & Review

```text
POST /api/work/
GET  /api/work/{work_id}/
PUT  /api/work/{work_id}/
POST /api/work/{work_id}/submit/
POST /api/work/{work_id}/approve/
POST /api/work/{work_id}/reject/

POST /api/reviews/
GET  /api/reviews/{review_id}/
```

### Payment & Notification

```text
POST /api/payments/
GET  /api/payments/{payment_id}/
GET  /api/payments/history/
POST /api/payments/{payment_id}/process/

POST /api/notifications/
GET  /api/notifications/
```

## Contract changes

If an endpoint, request field, response field, authentication requirement, or status value changes, update this document and notify the frontend/service owners before merging.
