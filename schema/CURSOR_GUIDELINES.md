# CURSOR_GUIDELINES

Concise rules for the revmatch backend and repo. Follow these when adding or changing code.

## Stack

- **API:** Async FastAPI only; use `async def` for route handlers and I/O.
- **Database:** PyMongo async API (async MongoDB driver). No sync DB drivers in app code.

## Secrets and config

- **No secrets in repo.** Do not commit connection strings, API keys, or passwords. Use environment variables or a secret manager.
- **Config:** Read all env via Pydantic Settings (e.g. `pydantic-settings`). Use a single settings module (e.g. `app.config`) and inject where needed.

## Structure

- **Business logic in services.** Routes must stay thin: parse request, call a service, return response. No aggregation or DB logic in route modules.
- **Routes:** Mount under a clear path (e.g. `/health`, `/recommendations`). Keep route modules in `app/routes/`, services in `app/services/`.

## Endpoints

- **Health:** Expose `GET /health` returning 200 and a simple payload (e.g. `{"status": "ok"}`). Optionally include DB ping.
- **Recommendations:** Expose `GET /recommendations` that implements the existing aggregation over `porsche` (trims + specSheets, and optionally characterScores, for market US). Delegate to a recommendations service; support optional query params (e.g. year, limit) as needed.

## Ops and quality

- **Dockerfile:** Include a production-ready Dockerfile (e.g. `python:3.12-slim`). Do not bake secrets into the image; require `MONGO_URI` (or equivalent) at runtime.
- **Requirements:** Maintain a `requirements.txt` with pinned dependencies (FastAPI, uvicorn, pymongo[srv], pydantic-settings).
- **README:** Document how to run locally and how to build/deploy with Docker (including required env vars).
- **Tests:** Include basic tests: at least health endpoint and recommendations endpoint (mock service or test DB). Runnable via `pytest` or the project’s test runner.
