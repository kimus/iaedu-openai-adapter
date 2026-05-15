"""
IAedu → OpenAI proxy compatible with OpenWebUI.

Architectural decisions (all empirically validated):
- IAedu keeps server-side history per thread_id → send only the latest message.
- user_context is ignored by the server → system prompts are injected as a
  prefix in the first new message of the thread.
- temperature/max_tokens/top_p are ignored upstream → accepted but logged.
- Images do not work with this agent → reject them with a clear 400 response.
- Server-side timeout is 120s → httpx timeout is 130s.
- Concurrency on the same thread can cause 500 → asyncio.Lock per thread_id.
- Mid-stream cancellation makes IAedu "save" the response for the next request
  on the same thread → after cancellation, rotate thread_id.
- Tool/function calling is emulated by prompting the text-only upstream to emit
  JSON tool calls, then mapping them back to OpenAI-compatible tool_calls.
- No real usage is available → return zeroes.
"""

import asyncio
import json
import time
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .clients.upstream import open_iaedu_stream
from .core.auth import authenticate_for_chat, authenticate_for_listing
from .core.catalog import MODEL_CATALOG
from .core.config import LOG_LEVEL, PORT
from .core.state import CANCELLED_THREADS, THREAD_LOCKS, get_thread_lock
from .protocol.errors import IAEduUpstreamError, openai_error
from .protocol.responses import openai_chunk
from .protocol.schemas import ChatCompletionRequest
from .protocol.streaming import IAEduStreamState, parse_iaedu_events
from .protocol.tools import parse_tool_calls
from .protocol.translation import build_message_from_openai, derive_thread_id
from .utils.logger import log

app = FastAPI(title="IAedu → OpenAI Proxy")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "models_loaded": len(MODEL_CATALOG),
        "active_threads": len(THREAD_LOCKS),
        "cancelled_threads": len(CANCELLED_THREADS),
    }


@app.get("/v1/models")
async def list_models(authorization: Optional[str] = Header(default=None)):
    accessible = authenticate_for_listing(authorization)
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": m["name"],
                "object": "model",
                "created": now,
                "owned_by": "iaedu",
                "description": m.get("description", ""),
            }
            for m in accessible
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_thread_id: Optional[str] = Header(default=None, alias="X-Thread-Id"),
):
    model_cfg = authenticate_for_chat(authorization, body.model)

    ignored = []
    if body.temperature is not None:
        ignored.append("temperature")
    if body.max_tokens is not None:
        ignored.append("max_tokens")
    if body.top_p is not None:
        ignored.append("top_p")
    if body.presence_penalty is not None:
        ignored.append("presence_penalty")
    if body.frequency_penalty is not None:
        ignored.append("frequency_penalty")
    if body.stop is not None:
        ignored.append("stop")
    if ignored:
        log.debug("Ignored parameters (not supported upstream): %s", ignored)

    thread_id = derive_thread_id(x_thread_id, body.messages, body.model, body.user)

    try:
        message = build_message_from_openai(
            body.messages,
            thread_id,
            tools=body.tools,
            tool_choice=body.tool_choice,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise openai_error(400, str(e), "invalid_request", "bad_messages") from e

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    log.info(
        "📨 model='%s' thread='%s' stream=%s user='%s' msg_len=%s",
        model_cfg["name"],
        thread_id,
        body.stream,
        body.user or "-",
        len(message),
    )

    lock = await get_thread_lock(thread_id)

    if body.stream:
        return await _handle_streaming(
            body, model_cfg, thread_id, message, completion_id, created, lock, request
        )
    return await _handle_non_streaming(
        body, model_cfg, thread_id, message, completion_id, created, lock, request
    )


async def _handle_streaming(
    body: ChatCompletionRequest,
    model_cfg: dict,
    thread_id: str,
    message: str,
    completion_id: str,
    created: int,
    lock: asyncio.Lock,
    request: Request,
) -> StreamingResponse:
    async def event_generator():
        upstream_correlation: Optional[str] = None
        client_disconnected = False
        completed_normally = False
        tool_buffer: list[str] = []

        yield openai_chunk(
            completion_id,
            created,
            body.model,
            delta={"role": "assistant"},
            finish_reason=None,
        )

        try:
            async with lock:
                try:
                    async with open_iaedu_stream(
                        model_cfg=model_cfg,
                        message=message,
                        thread_id=thread_id,
                        user_id=body.user,
                    ) as (response, _client):
                        upstream_correlation = response.headers.get("x-correlation-id")
                        state = IAEduStreamState()

                        async for text in parse_iaedu_events(response, state):
                            if await request.is_disconnected():
                                client_disconnected = True
                                log.info(
                                    "Client disconnected (thread=%s, corr=%s) — marking thread as cancelled",
                                    thread_id,
                                    upstream_correlation,
                                )
                                break
                            if body.tools:
                                tool_buffer.append(text)
                            else:
                                yield openai_chunk(
                                    completion_id,
                                    created,
                                    body.model,
                                    delta={"content": text},
                                    finish_reason=None,
                                )

                        if client_disconnected:
                            CANCELLED_THREADS.add(thread_id)
                            return

                        if state.upstream_error:
                            log.warning(
                                "Upstream error mid-stream: %s (corr=%s, thread=%s)",
                                state.upstream_error,
                                upstream_correlation,
                                thread_id,
                            )
                            error_note = f"\n\n⚠️ [upstream error: {state.upstream_error}]"
                            if body.tools:
                                tool_buffer.append(error_note)
                            else:
                                yield openai_chunk(
                                    completion_id,
                                    created,
                                    body.model,
                                    delta={"content": error_note},
                                    finish_reason=None,
                                )

                        final_reason = state.finish_reason or "stop"
                        if body.tools:
                            buffered_text = "".join(tool_buffer)
                            tool_calls = parse_tool_calls(buffered_text)
                            if tool_calls:
                                for index, tool_call in enumerate(tool_calls):
                                    yield openai_chunk(
                                        completion_id,
                                        created,
                                        body.model,
                                        delta={"tool_calls": [{"index": index, **tool_call}]},
                                        finish_reason=None,
                                    )
                                final_reason = "tool_calls"
                            elif buffered_text:
                                yield openai_chunk(
                                    completion_id,
                                    created,
                                    body.model,
                                    delta={"content": buffered_text},
                                    finish_reason=None,
                                )

                        yield openai_chunk(
                            completion_id,
                            created,
                            body.model,
                            delta={},
                            finish_reason=final_reason,
                        )
                        completed_normally = True

                except IAEduUpstreamError as e:
                    log.error(
                        "Upstream error (thread=%s): status=%s msg=%s",
                        thread_id,
                        e.status,
                        e.message,
                    )
                    err_chunk = {
                        "error": {
                            "message": e.message,
                            "type": "upstream_error",
                            "code": e.code,
                        }
                    }
                    yield f"data: {json.dumps(err_chunk, ensure_ascii=False)}\n\n"
                    yield openai_chunk(completion_id, created, body.model, delta={}, finish_reason="stop")
                except httpx.TimeoutException:
                    log.error("Upstream timeout (thread=%s)", thread_id)
                    err_chunk = {
                        "error": {
                            "message": "Upstream timeout.",
                            "type": "upstream_timeout",
                            "code": "timeout",
                        }
                    }
                    yield f"data: {json.dumps(err_chunk, ensure_ascii=False)}\n\n"
                    yield openai_chunk(completion_id, created, body.model, delta={}, finish_reason="length")
                except Exception as e:
                    log.exception("Unexpected streaming error")
                    err_chunk = {
                        "error": {
                            "message": str(e),
                            "type": "proxy_error",
                            "code": "internal_error",
                        }
                    }
                    yield f"data: {json.dumps(err_chunk, ensure_ascii=False)}\n\n"
                    yield openai_chunk(completion_id, created, body.model, delta={}, finish_reason="stop")
        finally:
            yield "data: [DONE]\n\n"
            if not completed_normally and not client_disconnected:
                pass

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Thread-Id": thread_id,
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


async def _handle_non_streaming(
    body: ChatCompletionRequest,
    model_cfg: dict,
    thread_id: str,
    message: str,
    completion_id: str,
    created: int,
    lock: asyncio.Lock,
    request: Request,
) -> JSONResponse:
    upstream_correlation: Optional[str] = None
    try:
        async with lock:
            async with open_iaedu_stream(
                model_cfg=model_cfg,
                message=message,
                thread_id=thread_id,
                user_id=body.user,
            ) as (response, _client):
                upstream_correlation = response.headers.get("x-correlation-id")
                state = IAEduStreamState()
                async for _ in parse_iaedu_events(response, state):
                    if await request.is_disconnected():
                        CANCELLED_THREADS.add(thread_id)
                        log.info("Client disconnected in non-streaming mode (thread=%s)", thread_id)
                        return JSONResponse(
                            status_code=499,
                            content={
                                "error": {
                                    "message": "Client disconnected",
                                    "type": "client_disconnected",
                                    "code": "cancelled",
                                }
                            },
                        )

                full_text = "".join(state.tokens)
                if state.upstream_error:
                    log.warning(
                        "Upstream error in non-streaming mode: %s (corr=%s, thread=%s)",
                        state.upstream_error,
                        upstream_correlation,
                        thread_id,
                    )
                    if full_text:
                        full_text += f"\n\n⚠️ [upstream error: {state.upstream_error}]"
                    else:
                        raise IAEduUpstreamError(502, state.upstream_error, "upstream_stream_error")

    except IAEduUpstreamError as e:
        return JSONResponse(
            status_code=e.status,
            content={
                "error": {
                    "message": e.message,
                    "type": "upstream_error",
                    "code": e.code,
                }
            },
            headers={
                "X-Thread-Id": thread_id,
                **({"X-Upstream-Correlation-Id": upstream_correlation} if upstream_correlation else {}),
            },
        )
    except httpx.TimeoutException:
        log.error("Timeout upstream (thread=%s)", thread_id)
        return JSONResponse(
            status_code=504,
            content={
                "error": {
                    "message": "Upstream timeout.",
                    "type": "upstream_timeout",
                    "code": "timeout",
                }
            },
            headers={"X-Thread-Id": thread_id},
        )

    headers = {"X-Thread-Id": thread_id}
    if upstream_correlation:
        headers["X-Upstream-Correlation-Id"] = upstream_correlation

    message: dict = {"role": "assistant", "content": full_text}
    finish_reason = state.finish_reason or "stop"
    if body.tools:
        tool_calls = parse_tool_calls(full_text)
        if tool_calls:
            message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
            finish_reason = "tool_calls"

    return JSONResponse(
        content={
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": body.model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        },
        headers=headers,
    )


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level=LOG_LEVEL.lower(),
    )

if __name__ == "__main__":
    main()
