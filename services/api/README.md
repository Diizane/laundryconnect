# LaundryConnect API

FastAPI backend for LaundryConnect. See the [repository README](../../README.md)
and [docs/](../../docs/) for product context.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) recommended for environment management

## Setup

```bash
cd services/api
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/v1/health

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Configuration

Configuration is environment-based via `pydantic-settings`. See
[.env.example](.env.example) for all variables. Never commit a real `.env`.

| Variable       | Default       | Purpose                                    |
| -------------- | ------------- | ------------------------------------------ |
| `ENVIRONMENT`  | `development` | `development` / `test` / `production`      |
| `DEBUG`        | `false`       | Debug flag                                 |
| `LOG_LEVEL`    | `INFO`        | Root log level                             |
| `DATABASE_URL` | *(empty)*     | PostgreSQL DSN (used from Milestone 4)     |
| `CORS_ORIGINS` | *(empty)*     | Comma-separated allowed origins            |

## Structure

```
app/
  main.py           Application factory
  core/             Config, logging, middleware, error handling
  api/
    router.py       /api/v1 route aggregation
    routes/         Route modules (health; search etc. in later milestones)
  schemas/          Pydantic response/request models
  tests/            pytest suite
```

API docs are disabled when `ENVIRONMENT=production`.

## Notes

- `requirements.txt` is generated from `pyproject.toml`
  (`uv pip compile pyproject.toml -o requirements.txt`) and consumed by the
  Dockerfile. Edit dependencies in `pyproject.toml`, then regenerate.
- Structured JSON logs go to stdout; every request gets an `X-Request-ID`
  (incoming header honoured, otherwise generated).
- Errors return a structured envelope; stack traces are never sent to clients.
