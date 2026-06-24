from __future__ import annotations
from typing import Callable, Any

class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], Any]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> list[Any]:
        results = []
        for handler in self._subscribers.get(event_type, []):
            res = await handler(payload)
            if res is not None:
                results.append(res)
        return results

    def clear(self) -> None:
        self._subscribers.clear()

event_bus = EventBus()
