# user-service

**Owner:** Person 1

## Responsibility

Registration, login, JWT, profiles, roles, account management.

## Rules

- Own this service's data.
- Do not directly query another service's database.
- Use REST for service-to-service communication.
- Use JWT claims for authenticated user identity/role.
- Use UUIDs/IDs for references to entities owned by other services.
- Keep endpoint changes synchronized with `docs/api/API_CONTRACT.md`.

## Local Docker endpoint

`http://localhost:8001`

Health endpoint:

`http://localhost:8001/api/health/`
