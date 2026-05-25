from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    uri: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DataSourceRef:
    name: str
    uri: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisResult:
    title: str
    summary: str
    observations: list[str] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    provenance: list[DataSourceRef] = field(default_factory=list)
