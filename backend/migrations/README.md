# Database Migrations

StudyMate still calls `Base.metadata.create_all()` on startup for local demo convenience.
For schema upgrades, use Alembic from the `backend` directory:

```powershell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

The first revision mirrors the current SQLAlchemy models.
