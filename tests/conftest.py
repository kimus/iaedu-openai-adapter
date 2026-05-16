import json
import os


os.environ.setdefault(
    "MODELS_CONFIG",
    json.dumps(
        [
            {
                "name": "test-model",
                "description": "Model used by unit tests",
                "agent_id": "agent-1",
                "channel_id": "channel-1",
                "api_key_iaedu": "upstream-secret",
                "api_key_local": "local-secret",
            }
        ]
    ),
)
