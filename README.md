# iaedu-openai-adapter

OpenAI-compatible FastAPI proxy for IAedu agent streams.

The application uses a `src/` layout and loads local configuration from `.env` via `python-dotenv`.

## Setup with uv

```bash
uv sync
```

Create a local `.env` with either `MODELS_CONFIG_FILE` or `MODELS_CONFIG` plus any optional settings.

## Run

```bash
uv run iaedu-openai-adapter
# or
uv run uvicorn iaedu_openai_adapter.proxy:app --host 0.0.0.0 --port 3067
```

## Check

```bash
uv run python -m compileall src
curl http://localhost:3067/health
```
