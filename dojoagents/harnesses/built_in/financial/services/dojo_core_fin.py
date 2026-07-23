from __future__ import annotations

from typing import Any, Optional

from dojoagents.harnesses.built_in.financial.contracts.stock_fin_indicators import CoreTickerFinIndicatorsResponse
from dojoagents.harnesses.built_in.financial.contracts.stock_income import CoreTickerIncomeResponse
from dojoagents.harnesses.built_in.financial.services.fin_currency_conversion import (
    chained_conversion_factor,
    market_currency,
    normalize_currency,
    quarter_rate_window,
    required_forex_symbols,
)
from dojoagents.harnesses.built_in.financial.services.fin_indicators_utils import extract_report_date
from dojoagents.harnesses.built_in.financial.services.forex_store import ForexStore


def _currency_for_report(fin_rows: list[dict[str, Any]], report_date: str) -> Optional[str]:
    target = report_date[:10]
    if not target:
        return None
    for row in fin_rows:
        dates = {
            extract_report_date(row),
            str(row.get("std_report_date") or "")[:10],
        }
        if target not in dates:
            continue
        currency = normalize_currency(row.get("currency"))
        if currency:
            return currency
    return None


async def resolve_fin_indicators_for_market(
    response: CoreTickerFinIndicatorsResponse,
    *,
    forex_store: ForexStore | None,
) -> CoreTickerFinIndicatorsResponse:
    if forex_store is None or not response.items:
        return response
    converted_items = await forex_store.convert_fin_rows_to_market(response.items, response.market)
    return response.model_copy(update={"items": converted_items})


async def resolve_income_for_market(
    response: CoreTickerIncomeResponse,
    *,
    forex_store: ForexStore | None,
    fin_rows: list[dict[str, Any]],
    market: str,
) -> CoreTickerIncomeResponse:
    if forex_store is None or not response.distributions or not response.report_date:
        return response

    source = _currency_for_report(fin_rows, response.report_date)
    target = market_currency(market)
    if not source or source == target:
        return response

    window = quarter_rate_window(
        {
            "report_date": response.report_date,
            "std_report_date": response.report_date,
        }
    )
    if window is None:
        return response

    start, end = window
    symbols = required_forex_symbols([{"currency": source}], market)
    await forex_store.ensure_symbols_for_windows(symbols, [window])

    pair_closes: dict[str, float] = {}
    for symbol in symbols:
        avg = forex_store.average_close_for_range(symbol, start, end)
        if avg is not None and avg > 0:
            pair_closes[symbol] = avg
    if not pair_closes:
        return response

    try:
        factor = chained_conversion_factor(source, target, pair_closes)
    except ValueError:
        return response

    converted_distributions = []
    for slice_ in response.distributions:
        converted_items = []
        for item in slice_.items:
            converted_items.append(
                item.model_copy(
                    update={
                        "main_business_income": float(item.main_business_income) * factor,
                    }
                )
            )
        converted_distributions.append(slice_.model_copy(update={"items": converted_items}))

    return response.model_copy(update={"distributions": converted_distributions})
