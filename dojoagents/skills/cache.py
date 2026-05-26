from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

LOGGER = logging.getLogger("dojoagents.skills.cache")


class SkillPromptCache:
    def __init__(self, cache_file: Path | str) -> None:
        self.cache_file = Path(cache_file).expanduser()
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._disk_cache: Dict[str, Dict[str, Any]] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self.cache_file.exists():
            return
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._disk_cache = data
        except Exception as e:
            LOGGER.debug(f"Failed to load skill cache from {self.cache_file}: {e}")

    def _save_to_disk(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(
                json.dumps(self._disk_cache, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            LOGGER.debug(f"Failed to write skill cache to {self.cache_file}: {e}")

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

        # Check memory cache first
        mem_val = self._memory_cache.get(path_str)
        if mem_val and mem_val.get("mtime") == mtime and mem_val.get("size") == size:
            return mem_val["frontmatter"], mem_val["body"]

        # Check disk cache
        disk_val = self._disk_cache.get(path_str)
        if disk_val and disk_val.get("mtime") == mtime and disk_val.get("size") == size:
            self._memory_cache[path_str] = disk_val
            return disk_val["frontmatter"], disk_val["body"]

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

        cache_entry = {
            "mtime": mtime,
            "size": size,
            "frontmatter": frontmatter,
            "body": body,
        }
        self._memory_cache[path_str] = cache_entry
        self._disk_cache[path_str] = cache_entry
        self._save_to_disk()
