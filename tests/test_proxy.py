from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from iaedu_openai_adapter import proxy
from iaedu_openai_adapter.core.state import (
    CANCELLED_THREADS,
    THREAD_LOCKS,
    THREADS_WITH_SYSTEM_SENT,
)


class FakeResponse:
    def __init__(self, lines, headers=None):
        self._lines = lines
        self.headers = headers or {}

    async def aiter_bytes(self):
        for line in self._lines:
            yield (line + "\n").encode("utf-8")


class FakeUpstream:
    def __init__(self, lines=None, headers=None):
        self.calls = []
        self.lines = lines or [
            '{"type":"token","content":"Hello"}',
            '{"type":"token","content":" world"}',
            (
                '{"type":"message","content":'
                '{"response_metadata":{"stop_reason":"end_turn"}}}'
            ),
            '{"type":"done","messageId":"msg-1"}',
        ]
        self.headers = headers or {"x-correlation-id": "corr-1"}

    def stream(self, *, model_cfg, message, thread_id, user_id=None):
        self.calls.append(
            {
                "model_cfg": model_cfg,
                "message": message,
                "thread_id": thread_id,
                "user_id": user_id,
            }
        )

        @asynccontextmanager
        async def _ctx():
            yield FakeResponse(self.lines, self.headers), object()

        return _ctx()


def setup_function():
    CANCELLED_THREADS.clear()
    THREADS_WITH_SYSTEM_SENT.clear()
    THREAD_LOCKS.clear()


def test_models_requires_bearer_token():
    client = TestClient(proxy.app)

    response = client.get("/v1/models")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_api_key"


def test_models_lists_only_authorized_model():
    client = TestClient(proxy.app)

    response = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer local-secret"},
    )

    assert response.status_code == 200
    assert response.json()["object"] == "list"
    assert [model["id"] for model in response.json()["data"]] == ["test-model"]


def test_non_streaming_chat_returns_openai_response_and_forwards(monkeypatch):
    upstream = FakeUpstream()
    monkeypatch.setattr(proxy, "open_iaedu_stream", upstream.stream)
    client = TestClient(proxy.app)

    response = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": "Bearer local-secret",
            "X-Thread-Id": "thread-1",
        },
        json={
            "model": "test-model",
            "stream": False,
            "user": "user-1",
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Say hello"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.headers["x-thread-id"] == "thread-1"
    assert response.headers["x-upstream-correlation-id"] == "corr-1"
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "test-model"
    assert body["choices"][0]["message"] == {
        "role": "assistant",
        "content": "Hello world",
    }
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["usage"] == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    assert len(upstream.calls) == 1
    call = upstream.calls[0]
    assert call["thread_id"] == "thread-1"
    assert call["user_id"] == "user-1"
    assert call["model_cfg"]["agent_id"] == "agent-1"
    assert "Be concise." in call["message"]
    assert call["message"].endswith("Say hello")


def test_system_prompt_is_only_injected_once_per_thread(monkeypatch):
    upstream = FakeUpstream(
        lines=[
            '{"type":"token","content":"ok"}',
            '{"type":"done","messageId":"msg-1"}',
        ]
    )
    monkeypatch.setattr(proxy, "open_iaedu_stream", upstream.stream)
    client = TestClient(proxy.app)

    payload = {
        "model": "test-model",
        "messages": [
            {"role": "system", "content": "Persistent instruction"},
            {"role": "user", "content": "Question"},
        ],
    }
    headers = {
        "Authorization": "Bearer local-secret",
        "X-Thread-Id": "same-thread",
    }

    first = client.post("/v1/chat/completions", headers=headers, json=payload)
    second = client.post("/v1/chat/completions", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert "Persistent instruction" in upstream.calls[0]["message"]
    assert upstream.calls[1]["message"] == "Question"


def test_chat_rejects_images_before_calling_upstream(monkeypatch):
    upstream = FakeUpstream()
    monkeypatch.setattr(proxy, "open_iaedu_stream", upstream.stream)
    client = TestClient(proxy.app)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer local-secret"},
        json={
            "model": "test-model",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "https://example.test/img.png",
                            },
                        },
                    ],
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "vision_not_supported"
    assert upstream.calls == []
