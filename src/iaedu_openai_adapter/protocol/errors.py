"""Shared error helpers."""

import json

from fastapi import HTTPException


def openai_error(status: int, message: str, type_: str, code: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"message": message, "type": type_, "code": code}},
    )


class IAEduUpstreamError(Exception):
    """Upstream error with enough information to map it to an OpenAI error."""

    def __init__(self, status: int, message: str, code: str = "upstream_error"):
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


def map_upstream_error(status: int, body_text: str) -> IAEduUpstreamError:
    """Convert IAedu HTTP errors into clear messages."""
    try:
        body = json.loads(body_text)
    except Exception:
        body = {"detail": body_text}
    detail = body.get("detail", body_text)

    if status == 401:
        return IAEduUpstreamError(502, f"Upstream auth failed: {detail}", "upstream_auth_error")
    if status == 404:
        return IAEduUpstreamError(502, f"Upstream resource not found: {detail}", "upstream_not_found")
    if status == 422:
        return IAEduUpstreamError(502, f"Upstream validation: {detail}", "upstream_validation")
    if status == 500:
        return IAEduUpstreamError(502, f"Upstream internal error: {detail}", "upstream_internal")
    if status == 429:
        return IAEduUpstreamError(429, f"Upstream rate limited: {detail}", "upstream_rate_limited")
    return IAEduUpstreamError(502, f"Upstream HTTP {status}: {detail}", "upstream_error")
