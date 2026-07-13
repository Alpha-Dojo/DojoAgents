from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dojoagents.dashboard.services.session_input_ingest import read_session_input_slice
from dojoagents.dashboard.services.session_inputs import resolve_session_input_file
from dojoagents.tools.process_registry import active_session_id
from dojoagents.tools.registry import ToolSpec


def get_read_session_input_spec(sessions_root: str | Path) -> ToolSpec:
    root = Path(sessions_root).expanduser().resolve()

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        session_id = str(active_session_id.get() or args.get("session_id") or "").strip()
        if not session_id:
            raise RuntimeError("read_session_input requires an active agent session_id")

        filename = str(args.get("filename") or "").strip()
        if not filename:
            raise ValueError("filename is required")

        target = resolve_session_input_file(root, session_id, filename)
        if not target.is_file():
            raise FileNotFoundError(f"Session input file not found: {filename}")

        payload = read_session_input_slice(
            target,
            offset=int(args.get("offset") or 1),
            limit=int(args.get("limit") or 200),
            sheet=str(args.get("sheet")).strip() if args.get("sheet") else None,
        )
        return {
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
            "data": payload,
            "metadata": {
                "path": str(target),
                "filename": filename,
            },
        }

    return ToolSpec(
        name="read_session_input",
        description=(
            "Read a user-uploaded file from the current session inputs directory. "
            "Supports text/code/json/csv by line range, Excel by sheet row range, "
            "and PDF by page range. Use when the attachment preview is truncated."
        ),
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Basename of the uploaded session input file",
                },
                "offset": {
                    "type": "integer",
                    "description": "1-based line/page/row offset (default: 1)",
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum lines/pages/rows to return (default: 200)",
                    "default": 200,
                },
                "sheet": {
                    "type": "string",
                    "description": "Excel sheet name when reading .xlsx/.xls files",
                },
            },
            "required": ["filename"],
        },
        handler=_handler,
    )
