"""Helpers for prompt-based OpenAI tool/function calling compatibility."""

import json
import re
from typing import Any, Optional


def _normalize_tool(tool: dict) -> Optional[dict[str, Any]]:
    """Normalize OpenAI-style and common top-level tool schemas."""
    if tool.get("type") == "function":
        function = tool.get("function") or {}
    else:
        # Some clients/providers expose tools as top-level schemas instead of
        # OpenAI's {type:function,function:{...}} wrapper.
        function = tool

    name = function.get("name")
    if not isinstance(name, str) or not name:
        return None

    parameters = (
        function.get("parameters")
        or function.get("input_schema")
        or function.get("schema")
        or {"type": "object", "properties": {}}
    )
    return {
        "name": name,
        "description": function.get("description", ""),
        "parameters": parameters,
    }


def build_tool_instructions(
    tools: Optional[list[dict]],
    tool_choice: Optional[str | dict],
) -> str:
    """Build instructions that make a text-only upstream emit tool calls as JSON."""
    if not tools:
        return ""

    function_specs = [spec for tool in tools if (spec := _normalize_tool(tool))]

    if not function_specs:
        return ""

    choice_instruction = "Use a tool only when it is necessary to answer the user."
    if tool_choice == "none":
        choice_instruction = "Do not call any tools."
    elif tool_choice == "required":
        choice_instruction = "You must call one or more tools."
    elif isinstance(tool_choice, dict):
        forced_name = (tool_choice.get("function") or {}).get("name")
        if forced_name:
            choice_instruction = f"You must call the `{forced_name}` tool."

    tool_names = ", ".join(f"`{spec['name']}`" for spec in function_specs)
    return (
        "IMPORTANT: You are connected to an external tool runner. The tools are not "
        "executed inside this chat; they are executed by the client after you emit "
        "a tool call. Therefore, never say that you do not have access to tools, "
        "files, bash, read, write, edit, or the local environment. If a tool can "
        "help, emit a tool call.\n\n"
        f"Available tool names: {tool_names}\n"
        "Tool schemas:\n"
        f"{json.dumps(function_specs, ensure_ascii=False)}\n\n"
        f"{choice_instruction}\n"
        "When calling tools, respond with ONLY valid JSON in this exact shape:\n"
        '{"tool_calls":[{"name":"tool_name","arguments":{"arg":"value"}}]}\n'
        "The `arguments` object must match the selected tool schema.\n"
        "Do not wrap the JSON in Markdown. Do not add explanatory text when calling tools.\n"
        "If the user asks to inspect files, run commands, or modify files, call the relevant tool instead of refusing.\n"
        "If no tool is needed, answer normally."
    )


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped


def parse_tool_calls(text: str) -> Optional[list[dict]]:
    """Parse a model-emitted JSON tool call payload, if present."""
    candidate = _strip_markdown_fence(text)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    raw_calls = None
    if isinstance(payload, dict) and isinstance(payload.get("tool_calls"), list):
        raw_calls = payload["tool_calls"]
    elif isinstance(payload, dict) and isinstance(payload.get("tool_call"), dict):
        raw_calls = [payload["tool_call"]]
    elif isinstance(payload, dict) and payload.get("name") and "arguments" in payload:
        raw_calls = [payload]

    if not raw_calls:
        return None

    parsed: list[dict] = []
    for call in raw_calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else call
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            arguments_json = arguments
        else:
            arguments_json = json.dumps(arguments, ensure_ascii=False)
        parsed.append(
            {
                "id": call.get("id") or f"call_{len(parsed) + 1}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": arguments_json,
                },
            }
        )

    return parsed or None
