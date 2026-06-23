from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DataSource = Literal["sdk_online", "sdk_snapshot", "dashboard_cache", "computed"]
FreshnessSource = Literal[
    "sdk_online",
    "sdk_snapshot",
    "dashboard_cache",
    "computed",
    "local",
    "remote",
]


class FreshnessMeta(BaseModel):
    as_of: str | None = None
    source: DataSource
    stale: bool = False
