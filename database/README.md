# Database

The current deployment uses one PostgreSQL container with separate logical databases:

- `ctc_users`
- `ctc_projects`
- `ctc_applications`
- `ctc_work_reviews`
- `ctc_payments`

Each microservice owns its database.

Do not add cross-database foreign keys. Cross-service relationships are represented by IDs and resolved through REST APIs when necessary.

`init.sql` is executed only when the PostgreSQL data volume is initialized for the first time.
