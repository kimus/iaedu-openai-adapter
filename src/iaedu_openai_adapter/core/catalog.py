"""Model catalog loading."""

import json
import os
from pathlib import Path
from typing import Optional

from ..utils.logger import log

REQUIRED_FIELDS = ("name", "agent_id", "channel_id", "api_key_iaedu", "api_key_local")


def load_model_catalog() -> dict[str, dict]:
    """
    Load the catalog from one of these sources, in priority order:
      1. MODELS_CONFIG_FILE → path to a JSON file
      2. MODELS_CONFIG      → inline JSON environment variable
    """
    raw_json: Optional[str] = None
    source: str = ""

    config_file = os.getenv("MODELS_CONFIG_FILE", "").strip()
    if config_file:
        path = Path(config_file)
        if not path.exists():
            raise RuntimeError(f"MODELS_CONFIG_FILE inexistente: {path}")
        raw_json = path.read_text(encoding="utf-8")
        source = f"file {path}"
    else:
        raw_json = os.getenv("MODELS_CONFIG", "").strip()
        source = "MODELS_CONFIG variable"

    if not raw_json:
        raise RuntimeError(
            "No model catalog configured. "
            "Set MODELS_CONFIG (inline JSON) or MODELS_CONFIG_FILE."
        )

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in {source}: {e}")

    if not isinstance(parsed, list):
        raise RuntimeError(f"{source} deve ser um array JSON de modelos")

    catalog: dict[str, dict] = {}
    for idx, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            log.warning("Entry #%s ignored: not an object", idx)
            continue
        missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
        if missing:
            log.warning(
                "Model '%s' ignored: missing %s",
                entry.get("name", f"#{idx}"), missing,
            )
            continue
        name = entry["name"].strip().lower()
        if name in catalog:
            log.warning("Duplicate model '%s' — overwriting", name)
        catalog[name] = {
            "name": name,
            "description": entry.get("description", ""),
            "agent_id": entry["agent_id"],
            "channel_id": entry["channel_id"],
            "api_key_iaedu": entry["api_key_iaedu"],
            "api_key_local": entry["api_key_local"],
        }

    if not catalog:
        raise RuntimeError("No valid model was loaded from the catalog")
    return catalog


MODEL_CATALOG = load_model_catalog()
LOCAL_KEY_INDEX: dict[str, dict] = {
    cfg["api_key_local"]: cfg for cfg in MODEL_CATALOG.values()
}
log.info("✅ Models loaded (%s): %s", len(MODEL_CATALOG), list(MODEL_CATALOG.keys()))
