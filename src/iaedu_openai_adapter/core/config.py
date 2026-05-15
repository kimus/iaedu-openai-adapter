"""Application configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

IAEDU_BASE_URL = os.getenv(
    "IAEDU_BASE_URL", "https://api.iaedu.pt/agent-chat/api/v1/agent"
)
# Upstream server timeout is 120s; keep a 10s safety margin.
UPSTREAM_TIMEOUT_S = float(os.getenv("UPSTREAM_TIMEOUT_S", "130"))
# Retry on 500 errors, which can happen rarely with IAedu concurrency.
UPSTREAM_RETRY_500 = int(os.getenv("UPSTREAM_RETRY_500", "1"))
UPSTREAM_RETRY_BACKOFF_S = float(os.getenv("UPSTREAM_RETRY_BACKOFF_S", "0.5"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
PORT = int(os.getenv("PORT", "3067"))
