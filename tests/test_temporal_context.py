from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dojoagents.agent.temporal_context import build_temporal_context_block, resolve_timezone_iana


def test_resolve_timezone_iana_prefers_metadata():
    assert resolve_timezone_iana({"timezone_iana": "America/New_York"}) == "America/New_York"


def test_resolve_timezone_iana_falls_back_when_invalid():
    assert resolve_timezone_iana({"timezone_iana": "Not/AZone"}) == "Asia/Shanghai"


def test_resolve_timezone_iana_default_without_metadata():
    assert resolve_timezone_iana(None) == "Asia/Shanghai"


def test_build_temporal_context_block_uses_runtime_dates():
    fixed = datetime(2026, 7, 7, 4, 53, 0, tzinfo=timezone.utc)
    block = build_temporal_context_block(
        {"timezone_iana": "Asia/Shanghai"},
        now=fixed,
    )
    assert "2026-07-07T04:53:00+00:00" in block
    assert "2026-07-07T12:53:00+08:00 (Asia/Shanghai)" in block
    assert "Today (user): 2026-07-07" in block
    assert "do NOT add a year" in block


def test_build_temporal_context_block_converts_user_timezone():
    fixed = datetime(2026, 7, 7, 3, 0, 0, tzinfo=timezone.utc)
    block = build_temporal_context_block(
        {"timezone_iana": "America/New_York"},
        now=fixed,
    )
    local = fixed.astimezone(ZoneInfo("America/New_York"))
    assert local.replace(microsecond=0).isoformat() in block
    assert f"Today (user): {local.date().isoformat()}" in block
