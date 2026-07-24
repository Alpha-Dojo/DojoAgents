from ._adapter import FinancialResultPresenter

TICKER_RESULT_KINDS = (
    "get_ticker_realtime_quote",
    "get_ticker_price_trends",
    "get_ticker_financials",
    "get_ticker_company_profile",
    "search_company_ticker",
)

__all__ = ["FinancialResultPresenter", "TICKER_RESULT_KINDS"]
