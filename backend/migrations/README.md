# Database Migrations

Alembic is the only source of database schema changes. Application startup runs
`alembic upgrade head` and then verifies both the current revision and SQLite
foreign-key enforcement; it does not call `Base.metadata.create_all()` or issue
ad-hoc `ALTER TABLE` statements.

Create and validate schema changes from the `backend` directory:

```powershell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic check
```

Always back up production data before upgrading. Migration tests use temporary
databases and cover both an empty database and the previous Alembic head. A
narrow startup bridge recognizes known databases created by older `create_all`
releases, stamps their matching historical revision, and lets Alembic reconcile
the schema. Unknown or partial legacy schemas fail closed instead of being
modified heuristically.
