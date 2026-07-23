from __future__ import annotations

import os

import pytest

from tests.sessions.blob_contract import assert_blob_store_contract
from tests.sessions.external_factory import external_blob_store, external_session_store
from tests.sessions.store_contract import assert_session_store_contract


@pytest.mark.asyncio
async def test_external_session_store_complete_contract():
    if not os.environ.get("DOJO_TEST_SESSION_STORE_FACTORY"):
        pytest.skip("DOJO_TEST_SESSION_STORE_FACTORY is not configured")
    await assert_session_store_contract(await external_session_store())


@pytest.mark.asyncio
async def test_external_blob_store_complete_contract():
    if not os.environ.get("DOJO_TEST_BLOB_STORE_FACTORY"):
        pytest.skip("DOJO_TEST_BLOB_STORE_FACTORY is not configured")
    await assert_blob_store_contract(await external_blob_store())
