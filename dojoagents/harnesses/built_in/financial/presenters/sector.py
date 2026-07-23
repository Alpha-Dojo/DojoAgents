from ._adapter import FinancialResultPresenter

SECTOR_RESULT_KINDS = (
    "get_sector_movers",
    "get_sector_overview",
    "get_sector_constituents",
    "filter_sector_constituents",
)

__all__ = ["FinancialResultPresenter", "SECTOR_RESULT_KINDS"]
