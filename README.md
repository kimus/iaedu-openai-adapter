# iaedu-openai-adapter

OpenAI-compatible FastAPI proxy for IAedu agent streams.

The application uses a `src/` layout and loads local configuration from `.env` via `python-dotenv`.

## Setup with uv

```bash
uv sync
```

Create a local `.env` with either `MODELS_CONFIG_FILE` or `MODELS_CONFIG` plus any optional settings. See `.env.example`.

## Run locally

```bash
uv run iaedu-openai-adapter
# or
uv run uvicorn iaedu_openai_adapter.proxy:app --host 0.0.0.0 --port 3067
```

## Docker: build and run standalone

Build the image:

```bash
docker build -t iaedu-openai-adapter:local .
```

Create a `.env` file from `.env.example` and configure the model catalog using one of these options:

### Option A: inline model catalog, no volume required

Put the JSON catalog directly in `.env`:

```env
MODELS_CONFIG=[{"name":"example","description":"Example model","agent_id":"...","channel_id":"...","api_key_iaedu":"...","api_key_local":"..."}]
PORT=3067
```

Run:

```bash
docker run --rm \
  --name iaedu-openai-adapter \
  --env-file .env \
  -p 3067:3067 \
  iaedu-openai-adapter:local
```

### Option B: model catalog file, volume required

If `.env` uses `MODELS_CONFIG_FILE`, the file path must exist inside the container. For example:

```env
MODELS_CONFIG_FILE=/config/models.json
PORT=3067
```

Then mount the local file into the container:

```bash
docker run --rm \
  --name iaedu-openai-adapter \
  --env-file .env \
  -v "$(pwd)/models.json:/config/models.json:ro" \
  -p 3067:3067 \
  kimus/iaedu-openai-adapter:latest
```

Required configuration:

- `MODELS_CONFIG` or `MODELS_CONFIG_FILE`

Common optional configuration:

- `IAEDU_BASE_URL` defaults to `https://api.iaedu.pt/agent-chat/api/v1/agent`
- `PORT` defaults to `3067`
- `LOG_LEVEL`
- `UPSTREAM_TIMEOUT_S`
- `UPSTREAM_RETRY_500`
- `UPSTREAM_RETRY_BACKOFF_S`

Do not commit `.env` or files containing real API keys.

## Docker Compose: build and run

`compose.yaml` builds the Docker image from the local `Dockerfile`, publishes port `3067`, and loads environment variables from `.env`.

For inline `MODELS_CONFIG`, no extra volume is needed:

```bash
cp .env.example .env
# edit .env and set MODELS_CONFIG=...
docker compose up --build
```

For `MODELS_CONFIG_FILE`, use a container path in `.env`, for example:

```env
MODELS_CONFIG_FILE=/config/models.json
```

Then add a read-only volume to `compose.yaml`:

```yaml
services:
  iaedu-openai-adapter:
    build: .
    ports:
      - "3067:3067"
    env_file:
      - .env
    volumes:
      - ./models.json:/config/models.json:ro
```

Run with Compose:

```bash
docker compose up --build
```

Stop it with:

```bash
docker compose down
```

## Check

```bash
uv run python -m compileall src
curl http://localhost:3067/health
```
