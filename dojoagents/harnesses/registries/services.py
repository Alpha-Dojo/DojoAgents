from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ServiceRegistry:
    services: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "services", MappingProxyType(dict(self.services)))

    def require(self, service_id: str) -> Any:
        try:
            return self.services[service_id]
        except KeyError as exc:
            raise KeyError(f"service '{service_id}' is not available") from exc
