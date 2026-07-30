from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class SkillPromptCache:
    """In-process cache for parsed skill frontmatter/body, keyed by path+mtime+size."""

    def __init__(self) -> None:
        self._memory_cache: Dict[str, Dict[str, Any]] = {}

    def get(self, file_path: Path) -> Optional[Tuple[Dict[str, Any], str]]:
        path_str = str(file_path.resolve())
        if not file_path.exists():
            return None
        try:
            stat = file_path.stat()
            mtime = int(stat.st_mtime)
            size = stat.st_size
        except OSError:
            return None

        mem_val = self._memory_cache.get(path_str)
        if mem_val and mem_val.get("mtime") == mtime and mem_val.get("size") == size:
            return mem_val["frontmatter"], mem_val["body"]

        return None

    def set(self, file_path: Path, frontmatter: Dict[str, Any], body: str) -> None:
        path_str = str(file_path.resolve())
        if not file_path.exists():
            return
        try:
            stat = file_path.stat()
            mtime = int(stat.st_mtime)
            size = stat.st_size
        except OSError:
            return

        self._memory_cache[path_str] = {
            "mtime": mtime,
            "size": size,
            "frontmatter": frontmatter,
            "body": body,
        }
