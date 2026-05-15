# AGENTS.md

Project-specific instructions for pi/coding agents working in this repository.

## Project overview

This repository contains a small Python FastAPI proxy that exposes an OpenAI-compatible API for IAedu agent streams, intended for clients such as OpenWebUI.

Main files/directories:
- `src/iaedu_openai_adapter/proxy.py` — FastAPI app, OpenAI-compatible `/v1/models` and `/v1/chat/completions`, request handlers.
- `src/iaedu_openai_adapter/core/` — configuration, model catalog, auth, and in-memory state.
- `src/iaedu_openai_adapter/protocol/` — OpenAI-compatible schemas/responses/errors plus IAedu stream/message translation.
- `src/iaedu_openai_adapter/clients/` — external service clients, currently the IAedu HTTP streaming client.
- `src/iaedu_openai_adapter/utils/` — shared utilities, currently logging setup.
- `compose.yaml` — Docker Compose service `iaedu-proxy` exposing port `3067` and loading `.env`.
- `.env` — local secrets/configuration; do not print, commit, or expose its contents.

## Runtime assumptions

- Python entrypoint: `iaedu-openai-adapter` console script or module `iaedu_openai_adapter.proxy`.
- App object: `app = FastAPI(...)`.
- Default port: `3067` (`PORT` can override).
- Health endpoint: `GET /health`.
- OpenAI-compatible endpoints:
  - `GET /v1/models`
  - `POST /v1/chat/completions`

Dependencies are managed with `uv` in `pyproject.toml` / `uv.lock`.

Important environment variables:
- `MODELS_CONFIG_FILE` or `MODELS_CONFIG` — required model catalog.
- `IAEDU_BASE_URL` — defaults to `https://api.iaedu.pt/agent-chat/api/v1/agent`.
- `UPSTREAM_TIMEOUT_S`, `UPSTREAM_RETRY_500`, `UPSTREAM_RETRY_BACKOFF_S`.
- `LOG_LEVEL`, `PORT`.

## Development commands

Use `uv` for dependency management and command execution.

Install/sync dependencies:

```bash
uv sync
```

Basic syntax check:

```bash
uv run python -m compileall src
```

Run locally if dependencies and env are present:

```bash
uv run iaedu-openai-adapter
# or
uv run uvicorn iaedu_openai_adapter.proxy:app --host 0.0.0.0 --port 3067
```

Docker Compose:

```bash
docker compose up --build
```

Health check:

```bash
curl http://localhost:3067/health
```

## Coding conventions

- Keep the proxy OpenAI-compatible in response shapes and error objects.
- Keep user-facing messages in English.
- Avoid logging secrets: never log `api_key_iaedu`, `api_key_local`, bearer tokens, or raw `.env` contents.
- Maintain per-thread locking semantics; IAedu can fail on concurrent calls to the same `thread_id`.
- Be careful with cancellation behavior: cancelled streams are tracked in `CANCELLED_THREADS` to avoid stale upstream responses.
- Treat upstream limitations as deliberate behavior unless validated otherwise:
  - server-side IAedu history by `thread_id`
  - system prompts injected into first new message per thread
  - images unsupported
  - native upstream tools/function calling unsupported; this adapter emulates OpenAI tool calls with prompt-based JSON parsing
  - usage returned as zeroes

## Current repository notes

- `compose.yaml` uses `build: .` with the root `Dockerfile`.
- Python dependencies are managed by `uv` (`pyproject.toml` and `uv.lock`).
- No tests are currently present.
- The repository is not currently initialized as a git repository.

Before adding features, consider adding tests for request translation/error handling.
