# Development Guide

## Prerequisites

- Python 3.12+ ([uv](https://docs.astral.sh/uv/) recommended — it can install
  Python itself: `uv venv --python 3.12`)
- Docker + Docker Compose (optional, for the full stack with PostgreSQL)
- Git

## Backend setup

```bash
cd services/api
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env        # placeholders only; never commit .env
uv run uvicorn app.main:app --reload
```

- Docs UI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/v1/health

## Tests and linting

```bash
cd services/api
uv run pytest               # test suite
uv run ruff check .         # lint
uv run ruff format .        # format (CI runs format --check)
```

CI (`.github/workflows/ci.yml`) runs ruff check, ruff format --check, and
pytest on every push to main and every pull request. All three must pass.

## Docker

```bash
docker compose -f infrastructure/docker/docker-compose.yml up --build
```

Brings up the API on :8000 and PostgreSQL 16 on :5432. The compose credentials
are local-development-only placeholders.

## Database and migrations

The app runs without a database until `DATABASE_URL` is set (session-backed
endpoints return 503; readiness reports the check as skipped).

Apply migrations (uses `DATABASE_URL` from the environment):

```bash
cd services/api
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/laundryconnect \
  uv run alembic upgrade head
```

Create a new migration after changing models in `app/models/`:

```bash
DATABASE_URL=sqlite+aiosqlite:///./local-dev.db uv run alembic revision --autogenerate -m "describe change"
```

Review the generated file, run `ruff format` on it, and keep the
migration-parity test green (`app/tests/test_migrations.py`). Unit tests run
against SQLite (aiosqlite) — see ADR 0005 for the trade-offs.

Populate the catalog with clearly-labelled sample data (idempotent):

```bash
DATABASE_URL=... uv run python -m app.database.seed
```

## Dependency management

`services/api/pyproject.toml` is the source of truth. `requirements.txt` is
generated for Docker:

```bash
cd services/api
uv pip compile pyproject.toml -o requirements.txt
```

Regenerate it whenever `pyproject.toml` dependencies change.

## Git workflow

- Small logical commits on feature branches
  (`feature/...`, `fix/...`).
- Commit style: `feat(api): ...`, `test(api): ...`, `docs: ...`, `fix(api): ...`.
- Run tests and linting before committing.
- No force-pushes or history rewrites.

## Adding a new API route

1. Create a route module under `app/api/routes/`.
2. Define request/response schemas in `app/schemas/`.
3. Keep the handler thin; put logic in a service module.
4. Register the router in `app/api/router.py`.
5. Add tests under `app/tests/`.
6. Update documentation if behaviour or architecture changed.
