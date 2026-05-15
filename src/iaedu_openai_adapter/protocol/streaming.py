"""IAedu stream parsing."""

import json
from typing import AsyncGenerator, Optional

import httpx


def map_stop_reason(stop_reason: Optional[str]) -> str:
    if not stop_reason:
        return "stop"
    sr = stop_reason.lower()
    if sr in ("end_turn", "stop", "stop_sequence"):
        return "stop"
    if sr in ("max_tokens", "length"):
        return "length"
    if sr in ("tool_use", "tool_calls"):
        return "tool_calls"
    if sr in ("content_filter", "content_filtered"):
        return "content_filter"
    return "stop"


class IAEduStreamState:
    """Accumulated state while parsing a stream."""

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.finish_reason: str = "stop"
        self.upstream_error: Optional[str] = None
        self.run_id: Optional[str] = None
        self.message_id: Optional[str] = None
        self.model_name_real: Optional[str] = None


async def parse_iaedu_events(
    response: httpx.Response,
    state: IAEduStreamState,
) -> AsyncGenerator[str, None]:
    """Iterate response bytes and yield only new text token chunks."""
    buffer = ""
    async for chunk in response.aiter_bytes():
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            payload = line[5:].strip() if line.startswith("data:") else line
            if payload == "[DONE]":
                return
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue

            etype = obj.get("type", "")
            if etype == "start":
                state.run_id = obj.get("run_id")
            elif etype == "token":
                text = obj.get("content", "")
                if isinstance(text, str) and text:
                    state.tokens.append(text)
                    yield text
            elif etype == "message":
                inner = obj.get("content") or {}
                if isinstance(inner, dict):
                    md = inner.get("response_metadata") or {}
                    state.finish_reason = map_stop_reason(md.get("stop_reason"))
                    state.model_name_real = md.get("model_name")
            elif etype == "error":
                state.upstream_error = obj.get("content") or "upstream error"
                if state.tokens:
                    state.finish_reason = "length"
            elif etype == "done":
                state.message_id = obj.get("messageId")
                if state.message_id == "None" and not state.upstream_error:
                    state.upstream_error = "upstream did not complete"
                return

    if buffer.strip():
        try:
            obj = json.loads(buffer.strip())
            if obj.get("type") == "token":
                text = obj.get("content", "")
                if isinstance(text, str) and text:
                    state.tokens.append(text)
                    yield text
        except json.JSONDecodeError:
            pass
