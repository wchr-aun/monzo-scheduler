# Project guide

## Overview

This is a Python 3.14+ FastAPI service for scheduling Monzo savings-pot deposits and withdrawals.

## Structure

- `main.py` is the Uvicorn entry point and re-exports `app` and `create_app`.
- `app/main.py` constructs the FastAPI app, configures lifespan resources, and registers routers.
- `app/config.py` reads configuration from environment variables.
- `app/db/` defines SQLAlchemy models and database engine/session setup.
- `app/routers/` contains HTTP request handling. Keep API concerns here.
- `app/services/` contains scheduler and external Monzo API operations.
- `migrations/versions/` contains Alembic schema migrations.

Keep route handlers small. Put reusable business logic in services, and use FastAPI's app state or dependency injection for shared resources.

## Configuration and security

- Read secrets from environment variables; never hard-code or commit them.
- Keep the registered Monzo redirect URI aligned with `MONZO_REDIRECT_URI`.
- Preserve OAuth `state` validation on the callback.
- Do not log access tokens, client secrets, or authorization codes.
- Monzo access and refresh tokens are stored as plain text in SQLite so services can use them directly. Avoid exposing token values in logs or responses and protect the database file and backups.
- `JWT_SECRET_KEY` signs the application token returned by the OAuth callback.
- Apply schema changes with `uv run alembic upgrade head`; do not use `metadata.create_all()` in application startup.
- The scheduler and OAuth state are currently process-local, so the prototype assumes one worker.

## Development

Install dependencies with `uv sync`, then run `uv run uvicorn main:app --reload`. Declare dependencies in `pyproject.toml` and commit the corresponding `uv.lock` updates.

The health endpoint is `GET /health`. The API schema is available at `/docs` while the server is running. Configure `DATABASE_URL`, Monzo credentials, and `JWT_SECRET_KEY` in the environment before enabling OAuth.

## Tests

Run the unit and integration suite with `uv run pytest`. Unit tests cover local logic and error branches; integration tests use `respx` to mock Monzo's HTTP responses while exercising the app's HTTP flow. Keep integration tests deterministic and offline.
