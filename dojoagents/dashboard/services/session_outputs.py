from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dojoagents.sessions.identifiers import validate_output_filename, validate_session_id
from dojoagents.logging import LOGGER
from dojoagents.tools.session_file_tool import (
    resolve_session_output_dir,
)


def resolve_session_output_file(
    sessions_root: str | Path,
    session_id: str,
    filename: str,
) -> Path:
    safe_session = validate_session_id(session_id)
    safe_name = validate_output_filename(filename)
    output_dir = resolve_session_output_dir(sessions_root, safe_session).resolve()
    target = (output_dir / safe_name).resolve()
    if target.parent != output_dir:
        raise ValueError(f"invalid output path for filename: {filename!r}")
    return target


def list_session_output_files(
    sessions_root: str | Path,
    session_id: str,
) -> dict[str, Any]:
    safe_session = validate_session_id(session_id)
    output_dir = resolve_session_output_dir(sessions_root, safe_session)
    files: list[dict[str, Any]] = []
    if output_dir.is_dir():
        for path in sorted(output_dir.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            stat = path.stat()
            files.append(
                {
                    "filename": path.name,
                    "path": str(path.resolve()),
                    "bytes_written": stat.st_size,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
    return {
        "session_id": safe_session,
        "output_dir": str(output_dir.resolve()),
        "files": files,
    }


def reveal_path_in_file_manager(path: Path) -> None:
    target = path.resolve()
    if not target.exists():
        raise FileNotFoundError(f"file not found: {target}")

    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(target)], check=True)
        return
    if sys.platform == "win32":
        subprocess.run(["explorer", "/select,", str(target)], check=True)
        return
    if sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", str(target.parent)], check=True)
        return

    LOGGER.warning(
        "reveal_path_in_file_manager is unsupported on platform %s; opening parent directory",
        platform.system(),
    )
    subprocess.run(["xdg-open", str(target.parent)], check=True)
