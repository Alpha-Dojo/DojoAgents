from __future__ import annotations

from typing import Any


SESSION_ATTACHMENTS_PROTOCOL = """
## User-Uploaded Session Files

The user may attach files under `{sessions.root}/{session_id}/inputs/`.

- Each attachment includes an absolute `path`, `kind`, and usually a truncated `preview`.
- Use the preview first for quick analysis.
- When preview is truncated or you need more rows/pages/lines, call `read_session_input(filename, offset=..., limit=..., sheet=...)`.
- `execute_code` may read files directly from `DOJO_SESSION_INPUT_DIR` when set.
- Do NOT guess attachment paths or use terminal heredoc to access uploads.
""".strip()


def format_session_attachments_block(
    attachments: list[dict[str, Any]],
    *,
    locale: str = "en",
) -> str:
    if not attachments:
        return ""

    zh = str(locale or "en").startswith("zh")
    header = "## 用户上传文件" if zh else "## Attached Files"
    lines = [header]
    for item in attachments:
        filename = str(item.get("filename") or "").strip()
        path = str(item.get("path") or "").strip()
        kind = str(item.get("kind") or "file").strip()
        summary = str(item.get("summary") or "").strip()
        preview = str(item.get("preview_text") or "").strip()
        if not filename or not path:
            continue
        lines.append(f"- `{filename}` ({kind}) → `{path}`")
        if summary:
            lines.append(f"  - {summary}")
        if preview:
            lines.append("  ```")
            lines.append(preview)
            lines.append("  ```")
    return "\n".join(lines).strip()
