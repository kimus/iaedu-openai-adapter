"""OpenAI request to IAedu message/thread translation."""

import hashlib
import uuid
from typing import Optional, Union

from .errors import openai_error
from .schemas import ChatMessage
from .tools import build_tool_instructions
from ..core.state import CANCELLED_THREADS, THREADS_WITH_SYSTEM_SENT


def extract_text(content: Union[str, list[dict], None]) -> tuple[str, bool]:
    """Return (text, has_image). Concatenate text parts and flag images."""
    if content is None:
        return "", False
    if isinstance(content, str):
        return content, False
    if isinstance(content, list):
        parts: list[str] = []
        has_image = False
        for c in content:
            if not isinstance(c, dict):
                continue
            ctype = c.get("type")
            if ctype == "text":
                parts.append(c.get("text", "") or "")
            elif ctype in ("image_url", "input_image", "image"):
                has_image = True
        return "\n".join(parts), has_image
    return "", False


def build_message_from_openai(
    messages: list[ChatMessage],
    thread_id: str,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> str:
    """
    Build the message to send to IAedu.

    Since user_context is ignored upstream, inject system prompts as a prefix
    in the LAST user message, but only the first time this thread is seen.
    IAedu keeps server-side history, so repeating it is unnecessary.

    Detect images and reject them with a clear error.
    """
    if not messages:
        raise ValueError("messages array is required")

    last_message = next((m for m in reversed(messages) if m.role in ("user", "tool")), None)
    if not last_message:
        raise ValueError("No user or tool message found")

    user_text, user_has_image = extract_text(last_message.content)
    if last_message.role == "tool":
        tool_label = last_message.name or last_message.tool_call_id or "tool"
        user_text = f"Tool result from `{tool_label}`:\n{user_text}"

    if user_has_image:
        raise openai_error(
            400,
            "Images are not supported by this upstream model.",
            "unsupported_modality",
            "vision_not_supported",
        )

    if not user_text.strip():
        raise openai_error(400, "The user message is empty.", "invalid_request", "empty_message")

    system_parts: list[str] = []
    for m in messages:
        if m.role != "system":
            continue
        txt, has_img = extract_text(m.content)
        if has_img:
            raise openai_error(
                400,
                "Images in 'system' messages are not supported.",
                "unsupported_modality",
                "vision_not_supported",
            )
        if txt.strip():
            system_parts.append(txt.strip())

    system_text = "\n\n".join(system_parts).strip()
    prefix_parts: list[str] = []

    if system_text and thread_id not in THREADS_WITH_SYSTEM_SENT:
        THREADS_WITH_SYSTEM_SENT.add(thread_id)
        prefix_parts.append(
            "[SYSTEM INSTRUCTIONS — follow strictly in all responses]\n"
            f"{system_text}\n"
            "[END OF INSTRUCTIONS]"
        )

    # Tool definitions must be sent on every request where the client provides
    # tools. Unlike the system prompt, tool availability can change per turn and
    # the upstream has no native tool registry.
    tool_instructions = build_tool_instructions(tools, tool_choice)
    if tool_instructions:
        prefix_parts.append(
            "[TOOL CALLING INSTRUCTIONS — HIGHEST PRIORITY FOR THIS TURN]\n"
            f"{tool_instructions}\n"
            "If you decide to call a tool, do not say you lack access to it. "
            "Emit the required JSON tool call instead; the client will execute it.\n"
            "[END TOOL CALLING INSTRUCTIONS]"
        )

    if prefix_parts:
        message = "\n\n".join(prefix_parts) + f"\n\n{user_text}"
        if tool_instructions:
            # Repeat the critical part after the user message because some
            # upstream models overweight the final instruction.
            message += (
                "\n\nReminder: if this request needs files, shell commands, or edits, "
                "respond only with the JSON tool call. Do not claim you lack tool access."
            )
        return message

    return user_text


def derive_thread_id(
    x_thread_id: Optional[str],
    messages: list[ChatMessage],
    model_name: str,
    user_id: Optional[str] = None,
) -> str:
    """
    Strategy:
      1. If the client sent X-Thread-Id, use it.
      2. Otherwise, derive a deterministic hash from (user, model, first message).
      3. If the thread was marked as cancelled, generate a new derived thread_id.
    """
    if x_thread_id:
        return x_thread_id

    first_user = next((m for m in messages if m.role == "user"), None)
    if first_user is None:
        return uuid.uuid4().hex[:21]

    seed_text, _ = extract_text(first_user.content)
    raw = f"{user_id or 'anon'}|{model_name}|{seed_text}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    base_tid = digest[:21]

    tid = base_tid
    suffix = 0
    while tid in CANCELLED_THREADS:
        suffix += 1
        rotated = hashlib.sha256(f"{raw}|r{suffix}".encode("utf-8")).hexdigest()
        tid = rotated[:21]
        if suffix > 100:
            tid = uuid.uuid4().hex[:21]
            break
    return tid
