"""Authentication helpers for local API keys."""

from typing import Optional

from .catalog import LOCAL_KEY_INDEX, MODEL_CATALOG
from ..protocol.errors import openai_error


def extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


def authenticate_for_listing(authorization: Optional[str]) -> list[dict]:
    key = extract_bearer(authorization)
    if not key:
        raise openai_error(
            401,
            "Missing 'Authorization: Bearer <api_key>' header",
            "authentication_required",
            "missing_api_key",
        )
    model = LOCAL_KEY_INDEX.get(key)
    if not model:
        raise openai_error(401, "Invalid API key", "authentication_failed", "invalid_api_key")
    return [model]


def authenticate_for_chat(authorization: Optional[str], model_name: str) -> dict:
    key = extract_bearer(authorization)
    if not key:
        raise openai_error(
            401,
            "Missing 'Authorization: Bearer <api_key>' header",
            "authentication_required",
            "missing_api_key",
        )
    model_cfg = MODEL_CATALOG.get(model_name.lower())
    if not model_cfg:
        available = ", ".join(MODEL_CATALOG.keys())
        raise openai_error(
            404,
            f"Model '{model_name}' not found. Available: {available}",
            "model_not_found",
            "unknown_model",
        )
    if model_cfg["api_key_local"] != key:
        raise openai_error(
            403,
            f"The API key does not have access to model '{model_name}'",
            "forbidden",
            "model_access_denied",
        )
    return model_cfg
