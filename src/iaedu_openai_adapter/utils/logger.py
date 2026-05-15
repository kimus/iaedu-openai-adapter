"""Logging setup for the proxy."""

import logging

from ..core.config import LOG_LEVEL

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

log = logging.getLogger("iaedu-proxy")
