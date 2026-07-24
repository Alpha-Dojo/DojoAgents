from __future__ import annotations

import json
import os

from dojoagents.config.models import StoreProviderConfig
from dojoagents.sessions.factory import create_blob_store, create_session_store


def _options(name: str) -> dict:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


async def external_session_store():
    factory = os.environ["DOJO_TEST_SESSION_STORE_FACTORY"]
    return await create_session_store(
        StoreProviderConfig(
            provider="external-test",
            factory=factory,
            options=_options("DOJO_TEST_SESSION_STORE_OPTIONS"),
        )
    )


async def external_blob_store():
    factory = os.environ["DOJO_TEST_BLOB_STORE_FACTORY"]
    return await create_blob_store(
        StoreProviderConfig(
            provider="external-test",
            factory=factory,
            options=_options("DOJO_TEST_BLOB_STORE_OPTIONS"),
        )
    )
