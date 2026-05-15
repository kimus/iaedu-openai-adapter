"""IAedu upstream HTTP client."""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

import httpx

from ..core.config import (
    IAEDU_BASE_URL,
    UPSTREAM_RETRY_500,
    UPSTREAM_RETRY_BACKOFF_S,
    UPSTREAM_TIMEOUT_S,
)
from ..protocol.errors import IAEduUpstreamError, map_upstream_error
from ..utils.logger import log


@asynccontextmanager
async def open_iaedu_stream(
    model_cfg: dict,
    message: str,
    thread_id: str,
    user_id: Optional[str] = None,
):
    """
    Open the HTTP stream to IAedu. Retry once on 500 errors by default.
    Yield the httpx `response` object ready for `aiter_bytes()`.
    """
    url = f"{IAEDU_BASE_URL}/{model_cfg['agent_id']}/stream"
    data = {
        "channel_id": model_cfg["channel_id"],
        "thread_id": thread_id,
        "user_info": "{}",
        "message": message,
    }
    if user_id:
        data["user_id"] = user_id

    files = {k: (None, str(v)) for k, v in data.items()}
    headers = {"x-api-key": model_cfg["api_key_iaedu"]}
    timeout = httpx.Timeout(UPSTREAM_TIMEOUT_S, read=UPSTREAM_TIMEOUT_S)

    attempts = UPSTREAM_RETRY_500 + 1
    last_error: Optional[IAEduUpstreamError] = None

    for attempt in range(1, attempts + 1):
        client = httpx.AsyncClient(timeout=timeout)
        response_ctx = client.stream("POST", url, headers=headers, files=files)
        response = await response_ctx.__aenter__()

        if response.status_code == 200:
            try:
                yield response, client
            finally:
                try:
                    await response_ctx.__aexit__(None, None, None)
                finally:
                    await client.aclose()
            return

        body = await response.aread()
        body_text = body.decode("utf-8", errors="replace")
        await response_ctx.__aexit__(None, None, None)
        await client.aclose()

        last_error = map_upstream_error(response.status_code, body_text)
        log.warning(
            "Upstream error attempt %s/%s: status=%s body=%s",
            attempt,
            attempts,
            response.status_code,
            body_text[:300],
        )

        if response.status_code == 500 and attempt < attempts:
            await asyncio.sleep(UPSTREAM_RETRY_BACKOFF_S * attempt)
            continue
        break

    assert last_error is not None
    raise last_error
