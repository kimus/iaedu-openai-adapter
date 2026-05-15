"""OpenAI-compatible request schemas."""

from typing import Optional, Union

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: Union[str, list[dict], None] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[list[dict]] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    user: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[Union[str, list[str]]] = None
    tools: Optional[list[dict]] = None
    tool_choice: Optional[Union[str, dict]] = None
