from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from dojoagents.harnesses.built_in.financial.services.fin_indicators_utils import extract_report_date

MARKET_CURRENCY: Dict[str, str] = {
    "us": "USD",
    "hk": "HKD",
    "sh": "CNY",
}

FOREX_PAIR_SYMBOL: Dict[Tuple[str, str], str] = {
    ("USD", "CNY"): "USDCNY",
    ("HKD", "CNY"): "HKDCNY",
    ("HKD", "USD"): "HKDUSD",
}

CROSS_FX_CURRENCIES = frozenset({"CNY", "HKD", "USD"})
CROSS_FX_SYMBOLS = frozenset(FOREX_PAIR_SYMBOL.values())

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


def forex_symbols_for_currencies(source: str, target: str) -> List[str]:
    source = normalize_currency(source)
    target = normalize_currency(target)
    if source == target:
        return []
    if source in CROSS_FX_CURRENCIES and target in CROSS_FX_CURRENCIES:
        return sorted(CROSS_FX_SYMBOLS)
    direct = resolve_forex_pair_symbol(source, target)
    if direct:
        return [direct]
    inverse = resolve_forex_pair_symbol(target, source)
    if inverse:
        return [inverse]
    return []


def chained_conversion_factor(
    source: str,
    target: str,
    pair_closes: Dict[str, float],
) -> float:
    """
    Return multiplier: amount_in_source * factor = amount_in_target.

    Pair close conventions:
    - USDCNY: 1 USD = close CNY
    - HKDCNY: 1 HKD = close CNY
    - HKDUSD: 1 HKD = close USD
    """
    source = normalize_currency(source)
    target = normalize_currency(target)
    if source == target:
        return 1.0

    direct_symbol = resolve_forex_pair_symbol(source, target)
    if direct_symbol:
        close = pair_closes.get(direct_symbol)
        if close is not None and close > 0:
            return close

    inverse_symbol = resolve_forex_pair_symbol(target, source)
    if inverse_symbol:
        close = pair_closes.get(inverse_symbol)
        if close is not None and close > 0:
            return 1.0 / close

    if source == "CNY" and target == "HKD":
        usd_cny = pair_closes.get("USDCNY")
        hkd_usd = pair_closes.get("HKDUSD")
        if usd_cny and usd_cny > 0 and hkd_usd and hkd_usd > 0:
            return (1.0 / usd_cny) / hkd_usd
        raise ValueError("missing forex closes for CNY->HKD")

    if source == "HKD" and target == "CNY":
        hkdcny = pair_closes.get("HKDCNY")
        if hkdcny and hkdcny > 0:
            return hkdcny
        usd_cny = pair_closes.get("USDCNY")
        hkd_usd = pair_closes.get("HKDUSD")
        if usd_cny and usd_cny > 0 and hkd_usd and hkd_usd > 0:
            return hkd_usd * usd_cny
        raise ValueError("missing forex closes for HKD->CNY")

    if source == "CNY" and target == "USD":
        usd_cny = pair_closes.get("USDCNY")
        if usd_cny and usd_cny > 0:
            return 1.0 / usd_cny
        raise ValueError("missing forex close for CNY->USD")

    if source == "USD" and target == "CNY":
        usd_cny = pair_closes.get("USDCNY")
        if usd_cny and usd_cny > 0:
            return usd_cny
        raise ValueError("missing forex close for USD->CNY")

    if source == "USD" and target == "HKD":
        hkd_usd = pair_closes.get("HKDUSD")
        if hkd_usd and hkd_usd > 0:
            return 1.0 / hkd_usd
        raise ValueError("missing forex close for USD->HKD")

    if source == "HKD" and target == "USD":
        hkd_usd = pair_closes.get("HKDUSD")
        if hkd_usd and hkd_usd > 0:
            return hkd_usd
        raise ValueError("missing forex close for HKD->USD")

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
        symbols.update(forex_symbols_for_currencies(source, target))
    return sorted(symbols)
