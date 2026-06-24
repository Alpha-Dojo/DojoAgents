from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from dojoagents.dashboard.services.fin_indicators_utils import extract_report_date

MARKET_CURRENCY: Dict[str, str] = {
    "us": "USD",
    "hk": "HKD",
    "sh": "CNY",
}

FOREX_PAIR_SYMBOL: Dict[Tuple[str, str], str] = {
    ("USD", "CNY"): "USDCNYC",
    ("HKD", "CNY"): "HKDCNYC",
    ("HKD", "USD"): "HKDUSD",
}

FIN_MONETARY_FIELDS: Tuple[str, ...] = (
    "total_operating_revenue",
    "gross_profit_amount",
    "net_profit_attr_parent",
    "eps_basic",
    "eps_diluted",
    "eps_ttm",
    "operating_income_ps",
    "ocf_ps",
    "bps",
    "total_assets",
    "total_liabilities",
    "total_market_cap",
    "hksk_market_cap",
)


def normalize_currency(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"RMB", "CNH"}:
        return "CNY"
    return text


def market_currency(market: str) -> str:
    return MARKET_CURRENCY.get(market.lower(), "USD")


def quarter_rate_window(row: dict) -> Optional[Tuple[str, str]]:
    report_date = extract_report_date(row)
    if len(report_date) < 10:
        return None
    try:
        end = date.fromisoformat(report_date[:10])
    except ValueError:
        return None

    month_day = report_date[5:10]
    if month_day == "03-31":
        start = date(end.year, 1, 1)
    elif month_day == "06-30":
        start = date(end.year, 4, 1)
    elif month_day == "09-30":
        start = date(end.year, 7, 1)
    elif month_day == "12-31":
        start = date(end.year, 10, 1)
    else:
        accounting_start = extract_report_date({"std_report_date": row.get("accounting_start_date")})
        start_text = accounting_start or report_date[:10]
        try:
            start = date.fromisoformat(start_text[:10])
        except ValueError:
            return report_date[:10], end.isoformat()
        return start.isoformat(), end.isoformat()
    return start.isoformat(), end.isoformat()


def resolve_forex_pair_symbol(source: str, target: str) -> Optional[str]:
    source = normalize_currency(source)
    target = normalize_currency(target)
    if source == target:
        return None
    return FOREX_PAIR_SYMBOL.get((source, target))


def chained_conversion_factor(
    source: str,
    target: str,
    pair_closes: Dict[str, float],
) -> float:
    """
    Return multiplier: amount_in_source * factor = amount_in_target.

    Pair close conventions:
    - USDCNYC: 1 USD = close CNY
    - HKDCNYC: 1 HKD = close CNY
    - HKDUSD: 1 HKD = close USD
    """
    source = normalize_currency(source)
    target = normalize_currency(target)
    if source == target:
        return 1.0

    direct_symbol = resolve_forex_pair_symbol(source, target)
    if direct_symbol:
        close = pair_closes.get(direct_symbol)
        if close is None or close <= 0:
            raise ValueError(f"missing forex close for {direct_symbol}")
        return close

    inverse_symbol = resolve_forex_pair_symbol(target, source)
    if inverse_symbol:
        close = pair_closes.get(inverse_symbol)
        if close is None or close <= 0:
            raise ValueError(f"missing forex close for {inverse_symbol}")
        return 1.0 / close

    if source == "CNY" and target == "HKD":
        usd_cny = pair_closes.get("USDCNYC")
        hkd_usd = pair_closes.get("HKDUSD")
        if not usd_cny or not hkd_usd:
            raise ValueError("missing forex closes for CNY->HKD")
        return (1.0 / usd_cny) / hkd_usd

    if source == "HKD" and target == "CNY":
        hkdcny = pair_closes.get("HKDCNYC")
        if hkdcny and hkdcny > 0:
            return hkdcny
        usd_cny = pair_closes.get("USDCNYC")
        hkd_usd = pair_closes.get("HKDUSD")
        if not usd_cny or not hkd_usd:
            raise ValueError("missing forex closes for HKD->CNY")
        return hkd_usd * usd_cny

    raise ValueError(f"unsupported currency pair: {source}->{target}")


def convert_fin_row_amounts(
    row: dict,
    *,
    market: str,
    pair_closes: Dict[str, float],
) -> dict:
    source = normalize_currency(row.get("currency"))
    target = market_currency(market)
    if not source or source == target:
        return row

    try:
        factor = chained_conversion_factor(source, target, pair_closes)
    except ValueError:
        return row

    converted = dict(row)
    for field in FIN_MONETARY_FIELDS:
        value = converted.get(field)
        if value is None:
            continue
        try:
            converted[field] = float(value) * factor
        except (TypeError, ValueError):
            continue
    converted["currency"] = target
    return converted


def rows_need_currency_conversion(rows: Iterable[dict], market: str) -> bool:
    target = market_currency(market)
    for row in rows:
        source = normalize_currency(row.get("currency"))
        if source and source != target:
            return True
    return False


def required_forex_symbols(rows: Iterable[dict], market: str) -> List[str]:
    target = market_currency(market)
    symbols: set[str] = set()
    for row in rows:
        source = normalize_currency(row.get("currency"))
        if not source or source == target:
            continue
        if resolve_forex_pair_symbol(source, target):
            symbol = resolve_forex_pair_symbol(source, target)
            if symbol:
                symbols.add(symbol)
            continue
        if resolve_forex_pair_symbol(target, source):
            symbol = resolve_forex_pair_symbol(target, source)
            if symbol:
                symbols.add(symbol)
            continue
        if {source, target} == {"CNY", "HKD"}:
            symbols.update({"USDCNYC", "HKDUSD", "HKDCNYC"})
    return sorted(symbols)
