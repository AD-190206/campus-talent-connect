# Campus Talent Connect (CTC)

Campus Talent Connect is a student-focused freelancing platform. The backend is organized as five independently deployable Django REST microservices, with a Next.js frontend and an Nginx API gateway.

## Architecture

```text
Browser
   |
   v
Next.js Frontend :3000
   |
   v
Nginx API Gateway :8000
   |
   +--> User & Authentication Service :8001
   +--> Project Management Service    :8002
   +--> Application & Assignment      :8003
   +--> Work & Review Service          :8004
   +--> Payment & Notification Service :8005
                    |
                    v
              PostgreSQL :5432
```

For the current single-machine deployment, one PostgreSQL instance is used with separate logical databases for each service.

## Services

| Service | Port | Owner | Responsibility |
|---|---:|---|---|
| user-service | 8001 | Person 1 | Registration, login, JWT, profiles, roles |
| project-service | 8002 | Person 2 | Projects, search, filtering, lifecycle |
| application-service | 8003 | Person 3 | Applications, shortlisting, selection, assignments |
| work-review-service | 8004 | Person 4 | Deliverables, approval, completion, reviews |
| payment-notification-service | 8005 | Person 5 | Payments, transactions, gateway, notifications |

## Prerequisites

- Git
- Docker Desktop
- Docker Compose
- Node.js only if developing the frontend outside Docker
- Python 3.12 only if developing a backend service outside Docker

## First setup

```bash
git clone <repository-url>
cd campus-talent-connect

cp .env.example .env

docker compose up --build
```

Open:

- Frontend: http://localhost:3000
- API Gateway: http://localhost:8000

The individual backend services are also exposed on ports 8001–8005 for development/debugging.

## Development rules

1. Each person primarily works inside their assigned service directory.
2. A service owns its own data.
3. Never directly query another service's database.
4. Cross-service communication happens through REST APIs.
5. Use IDs such as `student_id`, `project_id`, and `assignment_id` across service boundaries instead of cross-database foreign keys.
6. Keep API contracts in `docs/api/API_CONTRACT.md`.
7. Do not commit `.env` or secrets.
8. Keep `main` stable; develop features in branches.

## Useful commands

Start everything:

```bash
docker compose up
```

Rebuild after dependency/code changes:

```bash
docker compose up --build
```

Run in background:

```bash
docker compose up -d
```

Stop:

```bash
docker compose down
```

Stop and remove volumes (destructive to local database data):

```bash
docker compose down -v
```

View logs:

```bash
docker compose logs -f
docker compose logs -f user-service
```

Check running containers:

```bash
docker compose ps
```

## Repository layout

```text
campus-talent-connect/
├── frontend/
├── gateway/
├── services/
│   ├── user-service/
│   ├── project-service/
│   ├── application-service/
│   ├── work-review-service/
│   └── payment-notification-service/
├── database/
├── docs/
└── scripts/
```
