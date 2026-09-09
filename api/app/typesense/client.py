"""Typesense clients. Admin key never leaves this process — the browser talks
to FastAPI only, never to Typesense directly."""
from functools import lru_cache

import typesense

from app.config import get_settings


@lru_cache
def admin_client() -> typesense.Client:
    s = get_settings()
    return typesense.Client(
        {
            "nodes": [
                {
                    "host": s.typesense_host,
                    "port": s.typesense_port,
                    "protocol": s.typesense_protocol,
                }
            ],
            "api_key": s.typesense_admin_api_key,
            "connection_timeout_seconds": 10,
        }
    )
