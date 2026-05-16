# iaedu-openai-adapter

OpenAI-compatible FastAPI proxy for IAedu agent streams.

Tested with [Pi](https://pi.dev).

The application uses a `src/` layout and loads local configuration from `.env` via `python-dotenv`.

## Quick start with Docker

The preferred way to run this project is with Docker and a separate `models.json` file mounted into the container.

Create a `models.json` file:

```json
[
  {
    "name": "Opus-4.7-AIedu",
    "description": "Claude Opus 4.7",
    "agent_id": "your-agent-id",
    "channel_id": "your-channel-id",
    "api_key_iaedu": "sk-usr-your-iaedu-api-key",
    "api_key_local": "aiedu"
  },
  {
    "name": "GPT-5.5-AIedu",
    "description": "ChatGPT 5.5",
    "agent_id": "your-agent-id",
    "channel_id": "your-channel-id",
    "api_key_iaedu": "sk-usr-your-iaedu-api-key",
    "api_key_local": "aiedu"
  }
]
```

Run the published Docker image:

```bash
docker run --rm \
  --name iaedu-openai-adapter \
  -e MODELS_CONFIG_FILE=/config/models.json \
  -v "$(pwd)/models.json:/config/models.json:ro" \
  -p 3067:3067 \
  kimus/iaedu-openai-adapter:latest
```

Check that the service is running:

```bash
curl http://localhost:3067/health
```

## Configuration

Required configuration:

- `MODELS_CONFIG_FILE`: path to a JSON model catalog file inside the container or local environment
- `MODELS_CONFIG`: inline JSON model catalog, used as an alternative to `MODELS_CONFIG_FILE`

Common optional configuration:

- `IAEDU_BASE_URL` defaults to `https://api.iaedu.pt/agent-chat/api/v1/agent`
- `PORT` defaults to `3067`
- `LOG_LEVEL`
- `UPSTREAM_TIMEOUT_S`
- `UPSTREAM_RETRY_500`
- `UPSTREAM_RETRY_BACKOFF_S`

Do not commit `.env`, `models.json`, or any other files containing real API keys.

## Example `.env`

Use this when running locally, with Docker Compose, or if you prefer passing configuration through `--env-file`.

```env
# Model catalog file mounted or available in the runtime environment
MODELS_CONFIG_FILE=/config/models.json
```

## Docker build and run

Build the image locally:

```bash
docker build -t iaedu-openai-adapter:local .
```

Run the local image with a mounted `models.json` file:

```bash
docker run --rm \
  --name iaedu-openai-adapter \
  -e MODELS_CONFIG_FILE=/config/models.json \
  -v "$(pwd)/models.json:/config/models.json:ro" \
  -p 3067:3067 \
  iaedu-openai-adapter:local
```

## Inline model catalog

If you do not want to mount a separate file, you can put the model catalog directly in `.env`:

```env
MODELS_CONFIG='[{"name":"example","description":"Example model","agent_id":"your-agent-id","channel_id":"your-channel-id","api_key_iaedu":"sk-usr-your-iaedu-api-key","api_key_local":"aiedu"}]'
PORT=3067
```

Then run Docker with the `.env` file:

```bash
docker run --rm \
  --name iaedu-openai-adapter \
  --env-file .env \
  -p 3067:3067 \
  kimus/iaedu-openai-adapter:latest
```

## Docker Compose

The project `compose.yaml` builds the Docker image from the local `Dockerfile`, publishes port `3067`, and loads environment variables from `.env`.

```bash
cp .env.example .env
# edit .env and set MODELS_CONFIG_FILE=/config/models.json
docker compose up --build
```

Example Compose service using the published Docker image and a mounted model catalog:

```yaml
services:
  iaedu-openai-adapter:
    image: kimus/iaedu-openai-adapter:latest
    environment:
      - MODELS_CONFIG_FILE=/config/models.json
    ports:
      - "3067:3067"
    volumes:
      - ./models.json:/config/models.json:ro
```

Run with Compose:

```bash
docker compose up
```

Stop it with:

```bash
docker compose down
```

## Local development

Install dependencies with `uv`:

```bash
uv sync
```

Run locally:

```bash
uv run iaedu-openai-adapter
# or
uv run uvicorn iaedu_openai_adapter.proxy:app --host 0.0.0.0 --port 3067
```

Check the code and service:

```bash
uv run python -m compileall src
curl http://localhost:3067/health
```
