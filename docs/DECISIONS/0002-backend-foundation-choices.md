# ADR 0002: Backend foundation choices

- Status: accepted
- Date: 2026-07-23

## Context

Milestone 1 establishes the FastAPI backend foundation. Several small
decisions shape everything built on top of it.

## Decisions

1. **App factory (`create_app()`)** instead of a module-level singleton
   assembled at import time. Tests build fresh apps with controlled
   environments; future workers/CLIs can too. A module-level `app` is still
   exported for uvicorn.
2. **pydantic-settings with a cached `get_settings()`** as the single
   configuration entry point. The app must start without a database until
   Milestone 4, so `DATABASE_URL` is optional for now.
3. **Structured JSON logging via stdlib logging** with a custom formatter and
   a request-ID contextvar, rather than adding structlog. Keeps dependencies
   minimal; the formatter also redacts sensitive keys as a defence-in-depth
   backstop (see docs/SECURITY.md).
4. **Structured error envelope**
   `{"error": {"code", "message", "request_id", "details?"}}` for all errors,
   with stack traces logged server-side only.
5. **`pyproject.toml` is the dependency source of truth**; `requirements.txt`
   is compiled from it (`uv pip compile`) solely for the Docker image build.
6. **Ruff for lint + format** (including bandit `S` rules); Black not added
   since `ruff format` covers it.
7. **Readiness endpoint reports the database check as `skipped`**, not `ok`,
   until a real check exists — health endpoints must reflect reality.

## Consequences

- Adding the database in Milestone 4 means: make `DATABASE_URL` required in
  production, add a real readiness check, and wire a session dependency — no
  restructuring.
- Dependencies stay minimal (fastapi, uvicorn, pydantic, pydantic-settings);
  anything else must justify itself.
