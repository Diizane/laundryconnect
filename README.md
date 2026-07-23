# LaundryConnect

LaundryConnect is a unified technical knowledge platform for commercial laundry
service technicians. It brings manuals, parts information, wiring diagrams,
technical bulletins, and diagnostic documentation from multiple provider portals
(Alliance Laundry Systems, Girbau, Richard Jay Service, and others in future)
into one fast, technician-focused application.

The official provider documents remain the source of truth. LaundryConnect makes
them easier to find, navigate, search, and reference.

## Repository layout

```
laundryconnect/
  docs/               Product and technical documentation
  apps/
    mobile/           Flutter technician app (not started yet)
    admin/            React admin portal (not started yet)
  services/
    api/              FastAPI backend (active)
  infrastructure/
    docker/           Docker Compose for local development
  .github/workflows/  CI (tests + linting)
```

## Current status

**Milestones 1–2 complete** (Foundation, Provider connector framework). The
backend provides:

- FastAPI application with versioned routes under `/api/v1`
- Health endpoints (`/api/v1/health`, `/health/live`, `/health/ready`)
- Provider connector framework: base interface, registry, parallel fan-out
  search with per-provider timeouts and partial-failure handling
- A mock provider connector serving clearly-labelled sample data
  (`data_origin=mock`) — **no real provider integrations exist yet**
- Provider status endpoint (`/api/v1/providers/status`)
- Environment-based configuration (`pydantic-settings`)
- Structured JSON logging with request IDs
- Structured error responses (no stack traces to clients)
- pytest test suite and Ruff linting
- Dockerfile and Docker Compose with PostgreSQL

Mock data is never presented as live data — every result carries an honest
`data_origin` label. See [docs/ROADMAP.md](docs/ROADMAP.md) for the plan.

## Quick start (backend)

Requires Python 3.12+ (managed easily with [uv](https://docs.astral.sh/uv/)).

```bash
cd services/api
uv venv --python 3.12
uv pip install -e ".[dev]"
cp .env.example .env
uv run uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/docs.

Run tests and linting:

```bash
cd services/api
uv run pytest
uv run ruff check .
```

With Docker (once Docker is available):

```bash
docker compose -f infrastructure/docker/docker-compose.yml up --build
```

## Documentation

- [Product vision](docs/PRODUCT_VISION.md)
- [MVP definition](docs/MVP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development guide](docs/DEVELOPMENT.md)
- [Security model](docs/SECURITY.md)
- [Provider connector design](docs/PROVIDER_CONNECTORS.md)
- [Data model](docs/DATA_MODEL.md)
- [Roadmap](docs/ROADMAP.md)
- [Architecture Decision Records](docs/DECISIONS/)

## Security

Provider credentials are highly sensitive. They live in environment variables
(or a secret manager), never in the repository, never in the mobile client, and
never in API responses or logs. See [docs/SECURITY.md](docs/SECURITY.md).
