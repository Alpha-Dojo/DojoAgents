from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

FIN_INDICATORS_DEFAULT_LIMIT = 20
FIN_INDICATORS_VERIFY_LIMIT = 1

HK_PERIOD_Q1 = "q1"
HK_PERIOD_INTERIM = "interim"
HK_PERIOD_Q3 = "q3"
HK_PERIOD_ANNUAL = "annual"

HK_PERIOD_PREVIOUS: Dict[str, Optional[str]] = {
    HK_PERIOD_Q1: None,
    HK_PERIOD_INTERIM: HK_PERIOD_Q1,
    HK_PERIOD_Q3: HK_PERIOD_INTERIM,
    HK_PERIOD_ANNUAL: HK_PERIOD_Q3,
}

HK_PERIOD_NAME_TO_KIND = {
    "一季报": HK_PERIOD_Q1,
    "中报": HK_PERIOD_INTERIM,
    "三季报": HK_PERIOD_Q3,
    "年报": HK_PERIOD_ANNUAL,
}

HK_REPORT_PERIOD_RE = re.compile(r"^(\d{4})年(一季报|中报|三季报|年报)$")


def report_type_for_market(market: str) -> str:
    """HK has cumulative quarterly data only; SH/US use single-quarter reports."""
    return "accumulate" if market == "hk" else "quarter"


def extract_report_date(row: dict) -> str:
    """Normalize report date to YYYY-MM-DD for comparison and sorting."""
    raw = row.get("std_report_date") or row.get("report_date") or ""
    text = str(raw).strip()
    if not text:
        return ""
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text:
        text = text.split(" ", 1)[0]
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return text[:10]


def extract_period_end_date(row: dict) -> str:
    """Actual fiscal period-end date (prefer report_date over vendor std calendarization)."""
    raw = row.get("report_date") or row.get("period_end") or row.get("std_report_date") or ""
    text = str(raw).strip()
    if not text:
        return ""
    if "T" in text:
        text = text.split("T", 1)[0]
    elif " " in text:
        text = text.split(" ", 1)[0]
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return text[:10]


def sort_fin_rows(rows: List[dict]) -> List[dict]:
    return sorted(rows, key=lambda row: (extract_report_date(row), str(row.get("report_period_name") or "")))


def merge_fin_rows(existing: List[dict], incoming: List[dict]) -> List[dict]:
    by_date: Dict[str, dict] = {}
    for row in existing:
        key = extract_report_date(row)
        if key:
            by_date[key] = row
    for row in incoming:
        key = extract_report_date(row)
        if key:
            by_date[key] = row
    return sort_fin_rows(list(by_date.values()))


def trim_fin_rows(rows: List[dict], limit: int) -> List[dict]:
    if limit <= 0 or len(rows) <= limit:
        return rows
    return rows[-limit:]


def latest_report_date(rows: List[dict]) -> Optional[str]:
    sorted_rows = sort_fin_rows(rows)
    if not sorted_rows:
        return None
    return extract_report_date(sorted_rows[-1]) or None


def _hk_period_kind(row: dict) -> Optional[Tuple[str, str]]:
    name = str(row.get("report_period_name") or "").strip()
    match = HK_REPORT_PERIOD_RE.match(name)
    if match:
        return match.group(1), HK_PERIOD_NAME_TO_KIND[match.group(2)]

    report_date = extract_report_date(row)
    if len(report_date) < 10:
        return None

    fiscal_year = report_date[:4]
    month_day = report_date[5:]
    if month_day == "03-31":
        return fiscal_year, HK_PERIOD_Q1
    if month_day == "06-30":
        return fiscal_year, HK_PERIOD_INTERIM
    if month_day == "09-30":
        return fiscal_year, HK_PERIOD_Q3
    if month_day == "12-31":
        return fiscal_year, HK_PERIOD_ANNUAL
    return None


def _subtract_metric(current: object, previous: object) -> Optional[float]:
    if current is None:
        return None
    current_value = float(current)
    if previous is None:
        return current_value
    return current_value - float(previous)


def _scale_metric(value: object, ratio: float) -> Optional[float]:
    if value is None:
        return None
    return float(value) * ratio


def _median_hk_annual_single_quarter_ratio(by_fy_period: Dict[str, dict]) -> Optional[float]:
    ratios: List[float] = []
    for key, annual_row in by_fy_period.items():
        if not key.endswith(f":{HK_PERIOD_ANNUAL}"):
            continue
        fiscal_year = key.split(":", 1)[0]
        q3_row = by_fy_period.get(f"{fiscal_year}:{HK_PERIOD_Q3}")
        if q3_row is None:
            continue
        annual_rev = annual_row.get("total_operating_revenue")
        q3_rev = q3_row.get("total_operating_revenue")
        if annual_rev is None or q3_rev is None:
            continue
        annual_value = float(annual_rev)
        q3_value = float(q3_rev)
        if annual_value <= 0:
            continue
        q4_single = annual_value - q3_value
        if q4_single <= 0 or q4_single >= annual_value:
            continue
        ratios.append(q4_single / annual_value)
    if not ratios:
        return None
    ratios.sort()
    mid = len(ratios) // 2
    if len(ratios) % 2:
        return ratios[mid]
    return (ratios[mid - 1] + ratios[mid]) / 2


def deaccumulate_hk_fin_rows(rows: List[dict]) -> List[dict]:
    """Convert HK cumulative revenue / net profit into single-quarter values."""
    sorted_rows = sort_fin_rows(rows)
    by_fy_period: Dict[str, dict] = {}

    for row in sorted_rows:
        meta = _hk_period_kind(row)
        if meta is None:
            continue
        fiscal_year, period_kind = meta
        by_fy_period[f"{fiscal_year}:{period_kind}"] = row

    annual_single_quarter_ratio = _median_hk_annual_single_quarter_ratio(by_fy_period)

    deaccumulated: List[dict] = []
    for row in sorted_rows:
        meta = _hk_period_kind(row)
        if meta is None:
            deaccumulated.append(row)
            continue

        fiscal_year, period_kind = meta
        previous_kind = HK_PERIOD_PREVIOUS.get(period_kind)
        if previous_kind is None:
            deaccumulated.append(row)
            continue

        previous = by_fy_period.get(f"{fiscal_year}:{previous_kind}")
        if previous is None:
            if period_kind == HK_PERIOD_ANNUAL and annual_single_quarter_ratio is not None:
                next_row = dict(row)
                next_row["total_operating_revenue"] = _scale_metric(
                    row.get("total_operating_revenue"),
                    annual_single_quarter_ratio,
                )
                next_row["net_profit_attr_parent"] = _scale_metric(
                    row.get("net_profit_attr_parent"),
                    annual_single_quarter_ratio,
                )
                deaccumulated.append(next_row)
                continue
            deaccumulated.append(row)
            continue

        next_row = dict(row)
        next_row["total_operating_revenue"] = _subtract_metric(
            row.get("total_operating_revenue"),
            previous.get("total_operating_revenue"),
        )
        next_row["net_profit_attr_parent"] = _subtract_metric(
            row.get("net_profit_attr_parent"),
            previous.get("net_profit_attr_parent"),
        )
        deaccumulated.append(next_row)

    return deaccumulated


COMPARABLE_QUARTERS = ("q1", "q2", "q3", "q4")

SEASON_LABEL_TO_QUARTER = {
    "一季度": "q1",
    "二季度": "q2",
    "三季度": "q3",
    "四季度": "q4",
}

REPORT_SUFFIX_TO_QUARTER: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"一季报|第一季报"), "q1"),
    (re.compile(r"中报|第二季报|二季度|半年"), "q2"),
    (re.compile(r"三季报|第三季报|三季度"), "q3"),
    (re.compile(r"年报|第四季报|四季度"), "q4"),
]

REPORT_DATE_TO_QUARTER = {
    "03-31": "q1",
    "06-30": "q2",
    "09-30": "q3",
    "12-31": "q4",
}

HK_PERIOD_TO_COMPARABLE = {
    HK_PERIOD_Q1: "q1",
    HK_PERIOD_INTERIM: "q2",
    HK_PERIOD_Q3: "q3",
    HK_PERIOD_ANNUAL: "q4",
}


def comparable_quarter_key(row: dict) -> Optional[Tuple[str, str]]:
    """Return (fiscal_year, q1|q2|q3|q4) for a fin indicator row."""
    hk_meta = _hk_period_kind(row)
    if hk_meta is not None:
        fiscal_year, period_kind = hk_meta
        quarter = HK_PERIOD_TO_COMPARABLE.get(period_kind)
        if quarter:
            return fiscal_year, quarter

    name = str(row.get("report_period_name") or "").strip()
    named = re.match(r"^(\d{4})年(.+)$", name)
    if named:
        for pattern, quarter in REPORT_SUFFIX_TO_QUARTER:
            if pattern.search(named.group(2)):
                return named.group(1), quarter

    season = str(row.get("season_label") or "").strip()
    if season in SEASON_LABEL_TO_QUARTER:
        report_date = extract_report_date(row)
        if len(report_date) >= 4:
            return report_date[:4], SEASON_LABEL_TO_QUARTER[season]

    report_date = extract_report_date(row)
    if len(report_date) >= 10:
        quarter = REPORT_DATE_TO_QUARTER.get(report_date[5:])
        if quarter:
            return report_date[:4], quarter
    return None


def calendar_quarter_from_iso_date(iso_date: str) -> Optional[Tuple[str, str]]:
    """Map an ISO date to the natural calendar quarter that contains it."""
    text = str(iso_date or "").strip()
    if len(text) < 7:
        return None
    year = text[:4]
    try:
        month = int(text[5:7])
    except ValueError:
        return None
    if month < 1 or month > 12:
        return None
    quarter = COMPARABLE_QUARTERS[(month - 1) // 3]
    return year, quarter


def natural_comparable_quarter_key(row: dict) -> Optional[Tuple[str, str]]:
    """Return (year, q1|q2|q3|q4) in natural calendar space for cross-ticker alignment.

    Fiscal report labels (e.g. APD ``2026年第二季报``) are remapped using the actual
    period-end date so they align with calendar-year peers (PLUG ``2026年一季报``).
    """
    period_end = extract_period_end_date(row)
    natural = calendar_quarter_from_iso_date(period_end)
    if natural is not None:
        return natural
    return comparable_quarter_key(row)


def prepare_single_quarter_rows(rows: List[dict], market: str) -> List[dict]:
    """Return fin rows with single-quarter revenue / net profit values."""
    sorted_rows = sort_fin_rows(rows)
    if market == "hk":
        return deaccumulate_hk_fin_rows(sorted_rows)
    return sorted_rows


def report_effective_date(row: dict) -> str:
    """First calendar day when a report's metrics may be used (day after std_report_date)."""
    report_date = extract_report_date(row)
    if not report_date:
        return ""
    try:
        return (date.fromisoformat(report_date) + timedelta(days=1)).isoformat()
    except ValueError:
        return ""


def quarter_key(fiscal_year: str, quarter: str) -> str:
    return f"{fiscal_year}:{quarter}"


def trailing_quarter_keys(fiscal_year: str, quarter: str, count: int = 4) -> List[Tuple[str, str]]:
    """Return the trailing ``count`` fiscal quarters ending at (fiscal_year, quarter)."""
    if quarter not in COMPARABLE_QUARTERS or count <= 0:
        return []
    year = int(fiscal_year)
    idx = COMPARABLE_QUARTERS.index(quarter)
    keys: List[Tuple[str, str]] = []
    for _ in range(count):
        keys.append((str(year), COMPARABLE_QUARTERS[idx]))
        idx -= 1
        if idx < 0:
            idx = len(COMPARABLE_QUARTERS) - 1
            year -= 1
    return keys


def build_quarter_net_profit_map(rows: List[dict]) -> Dict[str, float]:
    profit_by_quarter: Dict[str, float] = {}
    for row in rows:
        meta = comparable_quarter_key(row)
        if meta is None:
            continue
        fiscal_year, quarter = meta
        profit = row.get("net_profit_attr_parent")
        if profit is None:
            continue
        profit_by_quarter[quarter_key(fiscal_year, quarter)] = float(profit)
    return profit_by_quarter


def build_ttm_schedule(rows: List[dict]) -> List[Tuple[str, str, str]]:
    """Sorted (effective_date, fiscal_year, quarter) entries from fin reports."""
    schedule: List[Tuple[str, str, str]] = []
    for row in rows:
        effective = report_effective_date(row)
        meta = comparable_quarter_key(row)
        if not effective or meta is None:
            continue
        fiscal_year, quarter = meta
        schedule.append((effective, fiscal_year, quarter))
    schedule.sort(key=lambda item: (item[0], item[1], item[2]))
    deduped: List[Tuple[str, str, str]] = []
    for item in schedule:
        if deduped and deduped[-1][0] == item[0]:
            deduped[-1] = item
        else:
            deduped.append(item)
    return deduped


def ttm_net_profit_for_anchor(
    fiscal_year: str,
    quarter: str,
    profit_by_quarter: Dict[str, float],
) -> Optional[float]:
    keys = trailing_quarter_keys(fiscal_year, quarter, 4)
    if len(keys) < 4:
        return None
    total = 0.0
    for fy, q in keys:
        value = profit_by_quarter.get(quarter_key(fy, q))
        if value is None:
            return None
        total += value
    return total


def anchor_for_date(trade_date: str, schedule: List[Tuple[str, str, str]]) -> Optional[Tuple[str, str]]:
    if not schedule or not trade_date:
        return None
    anchor: Optional[Tuple[str, str]] = None
    for effective, fiscal_year, quarter in schedule:
        if effective <= trade_date:
            anchor = (fiscal_year, quarter)
        else:
            break
    return anchor
