from __future__ import annotations

import os
from dojoagents.dashboard.services.portfolio_store import PortfolioStore, INDEX_FILENAME


def test_portfolio_store_copies_defaults_when_empty(tmp_path) -> None:
    # Set the force copy flag in the environment
    os.environ["_FORCE_COPY_DEFAULTS"] = "1"
    try:
        # Instantiate PortfolioStore, which should trigger the copy logic
        store = PortfolioStore(tmp_path)
    finally:
        os.environ.pop("_FORCE_COPY_DEFAULTS", None)

    # Verify the root directory was created and default portfolios were copied
    assert store.root.exists()
    assert (store.root / INDEX_FILENAME).exists()

    # Check that portfolio JSON files other than index.json exist
    json_files = [p for p in store.root.glob("*.json") if p.name != INDEX_FILENAME]
    assert len(json_files) > 0

    # Verify that load_sync correctly reconciled index portfolios list
    assert len(store.list_index_rows()) > 0

    # Check that a specific default portfolio is loaded
    first_portfolio_id = json_files[0].stem
    raw = store.get_raw(first_portfolio_id)
    assert raw is not None
    assert raw["id"] == first_portfolio_id


def test_portfolio_store_does_not_copy_if_data_exists(tmp_path) -> None:
    # 1. Create a clean portfolio first
    os.environ["_FORCE_COPY_DEFAULTS"] = "0"
    try:
        store = PortfolioStore(tmp_path)
        store.create("My Custom Portfolio")
    finally:
        os.environ.pop("_FORCE_COPY_DEFAULTS", None)

    custom_files = [p for p in store.root.glob("*.json") if p.name != INDEX_FILENAME]
    assert len(custom_files) == 1

    # 2. Re-instantiate with force copy = True
    os.environ["_FORCE_COPY_DEFAULTS"] = "1"
    try:
        store2 = PortfolioStore(tmp_path)
    finally:
        os.environ.pop("_FORCE_COPY_DEFAULTS", None)

    # Verify no additional portfolio files were copied from defaults
    json_files = [p for p in store2.root.glob("*.json") if p.name != INDEX_FILENAME]
    assert len(json_files) == 1
    assert json_files[0].name == custom_files[0].name
