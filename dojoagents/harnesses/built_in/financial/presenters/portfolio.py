from ._adapter import FinancialResultPresenter

PORTFOLIO_RESULT_KINDS = (
    "portfolio_read_list",
    "portfolio_read_search",
    "portfolio_read_detail",
    "portfolio_write_create",
    "portfolio_write_delete",
    "portfolio_write_rename",
    "portfolio_write_add_candidate",
    "portfolio_write_remove_candidate",
    "portfolio_write_buy",
    "portfolio_write_sell",
    "portfolio_write_liquidate",
)

__all__ = ["FinancialResultPresenter", "PORTFOLIO_RESULT_KINDS"]
