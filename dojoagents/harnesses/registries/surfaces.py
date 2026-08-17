from dataclasses import dataclass

from ..capabilities import SurfaceAdapterSpec


@dataclass(frozen=True)
class SurfaceRegistry:
    adapters: tuple[SurfaceAdapterSpec, ...] = ()
