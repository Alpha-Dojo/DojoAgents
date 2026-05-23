from __future__ import annotations

from collections.abc import Callable

from dojoagents.config.loader import ConfigStore
from dojoagents.config.models import AgentsConfig


class ConfigWatcher:
    def __init__(self, store: ConfigStore) -> None:
        self.store = store
        self._callbacks: list[Callable[[AgentsConfig], None]] = []

    def subscribe(self, callback: Callable[[AgentsConfig], None]) -> None:
        self._callbacks.append(callback)

    def reload(self) -> AgentsConfig:
        snapshot = self.store.snapshot()
        for callback in self._callbacks:
            callback(snapshot)
        return snapshot
