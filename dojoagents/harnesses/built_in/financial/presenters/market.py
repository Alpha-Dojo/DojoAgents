from ._adapter import FinancialResultPresenter

MARKET_RESULT_KINDS = (
    "get_market_overview",
    "get_market_stats",
    "screen_market_stocks",
)

__all__ = ["FinancialResultPresenter", "MARKET_RESULT_KINDS"]
