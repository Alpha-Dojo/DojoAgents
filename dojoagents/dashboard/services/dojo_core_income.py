from __future__ import annotations

from typing import Any, List, Optional

from dojoagents.dashboard.services.stock_income_utils import is_aggregate_item_name, parse_report_date
from dojoagents.dashboard.schemas.stock_income import (
    CoreIncomeDistributionItem,
    CoreIncomeDistributionSlice,
)

MAINOP_TYPES = ("1", "2", "3")


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not parsed or parsed <= 0:
        return None
    return parsed


def build_income_distributions(rows: List[dict[str, Any]]) -> tuple[Optional[str], List[CoreIncomeDistributionSlice]]:
    """Keep only the latest report_date and group rows by mainop_type."""
    dated_rows = [row for row in rows if parse_report_date(row.get("report_date"))]
    if not dated_rows:
        return None, [CoreIncomeDistributionSlice(mainop_type=mainop_type, report_date=None, items=[]) for mainop_type in MAINOP_TYPES]

    latest_report_date = max(parse_report_date(row["report_date"]) or "" for row in dated_rows)
    latest_rows = [row for row in dated_rows if parse_report_date(row.get("report_date")) == latest_report_date and not is_aggregate_item_name(row.get("item_name"))]

    distributions: List[CoreIncomeDistributionSlice] = []
    for mainop_type in MAINOP_TYPES:
        type_rows = [row for row in latest_rows if str(row.get("mainop_type", "")).strip() == mainop_type]
        type_rows.sort(key=lambda row: (row.get("rank") is None, row.get("rank") or 999999))

        items: List[CoreIncomeDistributionItem] = []
        for row in type_rows:
            item_name = str(row.get("item_name") or "").strip()
            if is_aggregate_item_name(item_name):
                continue
            income = _parse_float(row.get("main_business_income"))
            if income is None:
                continue
            ratio = _parse_float(row.get("mbi_ratio"))
            items.append(
                CoreIncomeDistributionItem(
                    item_name=item_name or "—",
                    main_business_income=income,
                    mbi_ratio=ratio if ratio is not None else 0.0,
                )
            )

        distributions.append(
            CoreIncomeDistributionSlice(
                mainop_type=mainop_type,
                report_date=latest_report_date,
                items=items,
            )
        )

    return latest_report_date, distributions
