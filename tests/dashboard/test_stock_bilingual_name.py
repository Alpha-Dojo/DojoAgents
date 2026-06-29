from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.services.market_sector_lead import _stock_bilingual_name


def _stock(**overrides) -> Stock:
    base = {
        "ticker": "NVDA",
        "market": "us",
        "short_name": "NVIDIA Corporation",
        "long_name": "NVIDIA Corporation",
    }
    base.update(overrides)
    return Stock(**base)


def test_us_stock_uses_quote_name_for_zh_and_short_name_for_en() -> None:
    stock = _stock(
        stock_quote=StockQuote(
            ticker="NVDA",
            name="英伟达",
            last_price=192.16,
            pre_close=195.74,
            open=193.12,
            high=195.55,
            low=191.22,
            change=-3.58,
            change_percent=-1.83,
            volume=1,
            amount=1.0,
            avg_price=192.0,
            market_cap=1.0,
            turn_rate=0.0,
            pe=29.0,
            pb=23.0,
            dividend_yield=0.0,
        ),
    )

    names = _stock_bilingual_name(stock)

    assert names.zh == "英伟达"
    assert names.en == "NVIDIA Corporation"


def test_stock_falls_back_when_quote_name_missing() -> None:
    stock = _stock(short_name="Apple Inc.", long_name="Apple Inc.", stock_quote=None)

    names = _stock_bilingual_name(stock)

    assert names.zh == "Apple Inc."
    assert names.en == "Apple Inc."


def test_cn_stock_prefers_quote_name_over_english_short_name() -> None:
    stock = _stock(
        ticker="600519.SS",
        market="sh",
        short_name="KWEICHOW MOUTAI",
        long_name="Kweichow Moutai Co., Ltd.",
        stock_quote=StockQuote(
            ticker="600519.SS",
            name="贵州茅台",
            last_price=1.0,
            pre_close=1.0,
            open=1.0,
            high=1.0,
            low=1.0,
            change=0.0,
            change_percent=0.0,
            volume=1,
            amount=1.0,
            avg_price=1.0,
            market_cap=1.0,
            turn_rate=0.0,
            pe=1.0,
            pb=1.0,
            dividend_yield=0.0,
        ),
    )

    names = _stock_bilingual_name(stock)

    assert names.zh == "贵州茅台"
    assert names.en == "KWEICHOW MOUTAI"
