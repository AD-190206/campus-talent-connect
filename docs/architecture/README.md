# Architecture Documentation

Keep the current and revised architecture diagrams here.

Recommended files:

- `microservice-architecture.png`
- `microservice-architecture.puml`
- `system-architecture.png`

The architecture should show:

Browser -> Next.js -> Nginx API Gateway -> five backend services -> PostgreSQL.

The current deployment is single-machine; Docker Compose provides the deployment boundary.
