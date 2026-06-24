from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class RecordingResource:
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        async def call(**kwargs: Any) -> Any:
            self.calls.append((name, kwargs))
            response = self.responses.get(name)
            if isinstance(response, Exception):
                raise response
            if callable(response):
                return response(**kwargs)
            return response

        return call


class FakeDojo:
    def __init__(
        self,
        *,
        stocks: dict[str, Any] | None = None,
        sectors: dict[str, Any] | None = None,
        benchmark: dict[str, Any] | None = None,
        forex: dict[str, Any] | None = None,
    ) -> None:
        self.stocks = RecordingResource(stocks)
        self.sectors = RecordingResource(sectors)
        self.benchmark = RecordingResource(benchmark)
        self.forex = RecordingResource(forex)
