# application-service

**Owner:** Person 3

## Responsibility

Applications, duplicate prevention, shortlisting, selection and assignments.

## Rules

- Own this service's data.
- Do not directly query another service's database.
- Use REST for service-to-service communication.
- Use JWT claims for authenticated user identity/role.
- Use UUIDs/IDs for references to entities owned by other services.
- Keep endpoint changes synchronized with `docs/api/API_CONTRACT.md`.

## Local Docker endpoint

`http://localhost:8003`

Health endpoint:

`http://localhost:8003/api/health/`
