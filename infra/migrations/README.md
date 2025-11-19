# Database Migrations

Place your SQL migration files in this directory.  You can use a tool like
Alembic, SQLModel, or Prisma to generate migration scripts based on your
models.  For example, with Alembic:

```sh
alembic init infra/migrations
alembic revision --autogenerate -m "create initial tables"
alembic upgrade head
```

Ensure that your migrations run as part of your CI/CD pipeline and are
applied when spinning up your database in production.