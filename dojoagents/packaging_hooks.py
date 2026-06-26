"""Setuptools hooks for bundling the dashboard frontend into wheels."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from setuptools.command.build_py import build_py as _build_py
from setuptools.command.sdist import sdist as _sdist


def _web_dir() -> Path:
    return Path(__file__).resolve().parent / "dashboard" / "web"


def _cleanup_node_modules(web_dir: Path) -> None:
    node_modules = web_dir / "node_modules"
    if node_modules.exists():
        shutil.rmtree(node_modules)


def build_dashboard_frontend_for_packaging(*, web_dir: Path | None = None) -> None:
    """Run npm install/build for wheel packaging."""
    target = web_dir or _web_dir()
    package_json = target / "package.json"
    dist_index = target / "dist" / "index.html"

    if dist_index.is_file() and not package_json.is_file():
        return

    if not package_json.is_file():
        raise RuntimeError(f"Dashboard frontend sources not found at {target}. " "Expected package.json for npm build, or a pre-built dist/index.html.")

    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("Node.js/npm is required to build the DojoAgents wheel. " "Install Node.js >=18 and npm >=9, then retry.")

    subprocess.run([npm, "install"], cwd=target, check=True)
    subprocess.run([npm, "run", "build"], cwd=target, check=True)


class BuildPyCommand(_build_py):
    def run(self) -> None:
        web_dir = _web_dir()
        build_dashboard_frontend_for_packaging(web_dir=web_dir)
        try:
            super().run()
        finally:
            _cleanup_node_modules(web_dir)


class SdistCommand(_sdist):
    def run(self) -> None:
        web_dir = _web_dir()
        build_dashboard_frontend_for_packaging(web_dir=web_dir)
        try:
            super().run()
        finally:
            _cleanup_node_modules(web_dir)
