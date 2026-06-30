"""DojoAgents quantitative finance agent runtime."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dojoagents")
except PackageNotFoundError:
    from pathlib import Path

    _version_file = Path(__file__).resolve().parents[1] / "VERSION"
    __version__ = _version_file.read_text(encoding="utf-8").strip() if _version_file.is_file() else "0.0.0+unknown"

__all__ = ["__version__"]
