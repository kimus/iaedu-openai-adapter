FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=3067

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 3067

CMD ["uv", "run", "--frozen", "--no-sync", "uvicorn", "iaedu_openai_adapter.proxy:app", "--host", "0.0.0.0", "--port", "3067"]
