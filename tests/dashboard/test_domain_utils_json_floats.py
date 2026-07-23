from __future__ import annotations

import math

import pandas as pd

from dojoagents.harnesses.built_in.financial.services.domain_utils import finite_float, sanitize_records


def test_finite_float_replaces_nan_and_inf() -> None:
    assert finite_float(float("nan")) == 0.0
    assert finite_float(float("inf")) == 0.0
    assert finite_float(float("-inf")) == 0.0
    assert finite_float(None, default=-1.0) == -1.0
    assert finite_float(1.25) == 1.25


def test_sanitize_records_replaces_non_finite_floats_with_none() -> None:
    frame = pd.DataFrame(
        [
            {"ticker": "AAA", "daily_return_pct": float("nan"), "close": 10.0},
            {"ticker": "BBB", "daily_return_pct": 2.5, "close": float("inf")},
        ]
    )

    records = sanitize_records(frame)

    assert records[0]["daily_return_pct"] is None
    assert records[0]["close"] == 10.0
    assert records[1]["daily_return_pct"] == 2.5
    assert records[1]["close"] is None


def test_nan_is_truthy_so_or_fallback_does_not_sanitize() -> None:
    value = float("nan")
    assert math.isnan(value or 0.0)
