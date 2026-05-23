from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlatformEntry:
    name: str
    label: str
    adapter_factory: Callable[[Any], Any]
    required_env: list[str] = field(default_factory=list)
    install_hint: str = ""


class GatewayRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, PlatformEntry] = {}

    def register(self, entry: PlatformEntry) -> None:
        self._entries[entry.name] = entry

    def create_adapter(self, name: str, config: Any) -> Any:
        return self._entries[name].adapter_factory(config)

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": entry.name,
                "label": entry.label,
                "required_env": entry.required_env,
                "install_hint": entry.install_hint,
            }
            for entry in self._entries.values()
        ]
