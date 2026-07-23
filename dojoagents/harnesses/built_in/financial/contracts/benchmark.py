from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BilingualText(BaseModel):
    zh: Optional[str] = Field(None, description="Chinese text")
    en: Optional[str] = Field(None, description="English text")


class BenchmarkKline(BaseModel):
    datetime: str = Field(..., description="Datetime")
    close: float = Field(..., description="Close price")


class Benchmark(BaseModel):
    symbol: str = Field(..., description="Benchmark symbol")
    name: BilingualText = Field(BilingualText(zh=None, en=None), description="Benchmark display name")
    market: str = Field(..., description="Market code: sh, hk, us")
    kline: Optional[list[BenchmarkKline]] = Field(None, description="Benchmark kline")


class BenchmarkCard(BaseModel):
    """Index card payload for DojoMesh hero sparkline."""

    market: str = Field(..., description="Market code: sh, hk, us")
    symbol: str = Field(..., description="Benchmark symbol")
    name: BilingualText = Field(..., description="Display name")
    price: float = Field(..., description="Latest close price")
    change_percent: float = Field(..., description="Day change percent")
    kline: list[BenchmarkKline] = Field(..., description="Daily bars, oldest to newest")


class MarketBenchmarks(BaseModel):
    default_benchmark: str = Field(..., description="Default selected symbol")
    benchmarks: list[BenchmarkCard] = Field(default_factory=list)


class DojoMeshBenchmarksResponse(BaseModel):
    as_of: Optional[str] = Field(None, description="Latest trading date from kline")
    markets: dict[str, MarketBenchmarks] = Field(default_factory=dict)
