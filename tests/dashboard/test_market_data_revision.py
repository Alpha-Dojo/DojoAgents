from __future__ import annotations

import json
from pathlib import Path

from dojoagents.dashboard.services.constituent_kline_refresh_state import RefreshStateStore


def test_get_market_data_revision_prefers_updated_at(tmp_path: Path) -> None:
    store = RefreshStateStore(tmp_path)
    store.file_path.write_text(
        json.dumps(
            {
                "preload_offline_data": "2026-06-30",
                "preload_offline_data_updated_at": "2026-06-30T08:05:12+00:00",
            }
        ),
        encoding="utf-8",
    )
    revision = store.get_market_data_revision()
    assert revision["revision"] == "2026-06-30T08:05:12+00:00"
    assert revision["preload_date"] == "2026-06-30"
