"""Domain-neutral preview and slice readers for session input files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from dojoagents.logging import LOGGER

PREVIEW_CHAR_LIMIT = 8_000
PREVIEW_LINE_LIMIT = 200
CSV_PREVIEW_ROWS = 30
EXCEL_PREVIEW_ROWS = 20

TEXT_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".html",
        ".htm",
        ".css",
        ".sql",
        ".ini",
        ".log",
    }
)
CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".java",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".scala",
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".sh",
        ".bash",
        ".zsh",
        ".r",
        ".lua",
    }
)
EXCEL_EXTENSIONS = frozenset({".xlsx", ".xls"})
PDF_EXTENSIONS = frozenset({".pdf"})
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"})
IMAGE_MIME_BY_FORMAT = {
    "BMP": "image/bmp",
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
IMAGE_FORMAT_BY_SUFFIX = {
    ".bmp": "BMP",
    ".gif": "GIF",
    ".jpeg": "JPEG",
    ".jpg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}

SUPPORTED_UPLOAD_EXTENSIONS = TEXT_EXTENSIONS | CODE_EXTENSIONS | EXCEL_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_IMAGE_PIXELS = 25_000_000
DEFAULT_MAX_IMAGE_FRAMES = 100


class SessionInputImageError(ValueError):
    pass


class SessionInputImageInvalidError(SessionInputImageError):
    pass


class SessionInputImageTypeMismatchError(SessionInputImageError):
    pass


class SessionInputImageTooLargeError(SessionInputImageError):
    pass


class SessionInputImageAnimatedError(SessionInputImageError):
    pass


def detect_session_input_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in CODE_EXTENSIONS:
        return "code"
    if suffix in {".csv", ".tsv"}:
        return "csv"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix in EXCEL_EXTENSIONS:
        return "excel"
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    return "binary"


def inspect_session_input_image(
    path: str | Path,
    *,
    max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
    animated_gif_enabled: bool = False,
    max_frames: int = DEFAULT_MAX_IMAGE_FRAMES,
) -> dict[str, Any]:
    target = Path(path).resolve()
    expected_format = IMAGE_FORMAT_BY_SUFFIX.get(target.suffix.lower())
    if expected_format is None:
        raise SessionInputImageTypeMismatchError("unsupported image extension")
    try:
        with Image.open(target) as image:
            actual_format = str(image.format or "").upper()
            if actual_format != expected_format:
                raise SessionInputImageTypeMismatchError(f"image format {actual_format or 'unknown'} does not match {expected_format}")
            mime_type = IMAGE_MIME_BY_FORMAT.get(actual_format)
            if mime_type is None:
                raise SessionInputImageTypeMismatchError(f"unsupported image format: {actual_format or 'unknown'}")
            width, height = image.size
            if width <= 0 or height <= 0:
                raise SessionInputImageInvalidError("image dimensions must be positive")
            pixels = width * height
            if pixels > max(1, int(max_pixels)):
                raise SessionInputImageTooLargeError(f"image has {pixels} pixels, limit is {max_pixels}")
            frame_count = int(getattr(image, "n_frames", 1) or 1)
            if frame_count > max(1, int(max_frames)):
                raise SessionInputImageTooLargeError(f"image has {frame_count} frames, limit is {max_frames}")
            if frame_count > 1 and not animated_gif_enabled:
                raise SessionInputImageAnimatedError("animated images are unsupported")
            image.load()
    except SessionInputImageError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise SessionInputImageInvalidError("image content cannot be decoded") from exc
    return {
        "kind": "image",
        "summary": (f"{mime_type} image, {width}x{height}, {frame_count} frame(s), " f"{target.stat().st_size:,} bytes"),
        "preview_text": "",
        "truncated": False,
        "content_type": mime_type,
        "width": width,
        "height": height,
        "frame_count": frame_count,
    }


def _truncate_text(text: str, *, char_limit: int = PREVIEW_CHAR_LIMIT) -> tuple[str, bool]:
    if len(text) <= char_limit:
        return text, False
    return text[:char_limit] + "\n…", True


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _preview_text_like(path: Path, kind: str) -> dict[str, Any]:
    text = _read_text_file(path)
    preview, truncated = _truncate_text(text)
    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    summary = f"{kind} file, {line_count:,} lines, {path.stat().st_size:,} bytes"
    if truncated:
        summary += f", preview first {PREVIEW_CHAR_LIMIT:,} chars"
    return {
        "kind": kind,
        "summary": summary,
        "preview_text": preview,
        "truncated": truncated,
        "line_count": line_count,
    }


def _preview_csv(path: Path) -> dict[str, Any]:
    import pandas as pd

    frame = pd.read_csv(path, nrows=CSV_PREVIEW_ROWS)
    preview = frame.to_csv(index=False)
    preview, truncated = _truncate_text(preview)
    summary = f"csv file, {len(frame.columns)} columns, preview {min(len(frame), CSV_PREVIEW_ROWS)} rows"
    return {
        "kind": "csv",
        "summary": summary,
        "preview_text": preview,
        "truncated": truncated or path.stat().st_size > PREVIEW_CHAR_LIMIT,
        "columns": [str(item) for item in frame.columns.tolist()],
        "preview_rows": len(frame),
    }


def _preview_excel(path: Path) -> dict[str, Any]:
    import pandas as pd

    workbook = pd.ExcelFile(path)
    sheets: list[dict[str, Any]] = []
    preview_parts: list[str] = []
    for sheet_name in workbook.sheet_names[:5]:
        frame = pd.read_excel(path, sheet_name=sheet_name, nrows=EXCEL_PREVIEW_ROWS)
        sheets.append(
            {
                "name": sheet_name,
                "columns": [str(item) for item in frame.columns.tolist()],
                "preview_rows": len(frame),
            }
        )
        preview_parts.append(f"## Sheet: {sheet_name}\n{frame.to_csv(index=False)}")
    preview, truncated = _truncate_text("\n\n".join(preview_parts))
    summary = f"excel file, {len(workbook.sheet_names)} sheet(s): {', '.join(workbook.sheet_names[:5])}"
    return {
        "kind": "excel",
        "summary": summary,
        "preview_text": preview,
        "truncated": truncated,
        "sheets": sheets,
    }


def _preview_pdf(path: Path) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = len(reader.pages)
    chunks: list[str] = []
    for index, page in enumerate(reader.pages[:10]):
        page_text = page.extract_text() or ""
        if page_text.strip():
            chunks.append(f"## Page {index + 1}\n{page_text}")
    text = "\n\n".join(chunks)
    preview, truncated = _truncate_text(text)
    summary = f"pdf file, {pages} page(s)"
    if truncated:
        summary += f", preview first {min(10, pages)} page(s)"
    return {
        "kind": "pdf",
        "summary": summary,
        "preview_text": preview,
        "truncated": truncated,
        "page_count": pages,
    }


def ingest_session_input_preview(path: str | Path) -> dict[str, Any]:
    target = Path(path).resolve()
    if not target.is_file():
        raise FileNotFoundError(f"input file not found: {target}")

    suffix = target.suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError(f"unsupported input file type: {suffix or '(no extension)'}")

    kind = detect_session_input_kind(target.name)
    try:
        if suffix in EXCEL_EXTENSIONS:
            payload = _preview_excel(target)
        elif suffix in PDF_EXTENSIONS:
            payload = _preview_pdf(target)
        elif suffix in IMAGE_EXTENSIONS:
            payload = inspect_session_input_image(target)
        elif suffix in {".csv", ".tsv"}:
            payload = _preview_csv(target)
        else:
            payload = _preview_text_like(target, kind)
    except Exception as exc:
        LOGGER.exception("Failed to ingest session input preview for %s", target)
        raise ValueError(f"failed to preview {target.name}: {exc}") from exc

    return {
        "filename": target.name,
        "path": str(target),
        "bytes": target.stat().st_size,
        **payload,
    }


def read_session_input_slice(
    path: str | Path,
    *,
    offset: int = 1,
    limit: int = PREVIEW_LINE_LIMIT,
    sheet: str | None = None,
) -> dict[str, Any]:
    target = Path(path).resolve()
    if not target.is_file():
        raise FileNotFoundError(f"input file not found: {target}")

    safe_offset = max(1, int(offset or 1))
    safe_limit = max(1, min(int(limit or PREVIEW_LINE_LIMIT), 2_000))
    suffix = target.suffix.lower()
    kind = detect_session_input_kind(target.name)

    if suffix in IMAGE_EXTENSIONS:
        return {
            "filename": target.name,
            "path": str(target),
            **inspect_session_input_image(
                target,
                animated_gif_enabled=True,
            ),
        }

    if suffix in EXCEL_EXTENSIONS:
        import pandas as pd

        frame = pd.read_excel(target, sheet_name=sheet or 0)
        start = safe_offset - 1
        end = start + safe_limit
        sliced = frame.iloc[start:end]
        return {
            "kind": "excel",
            "filename": target.name,
            "path": str(target),
            "sheet": sheet or (pd.ExcelFile(target).sheet_names[0] if pd.ExcelFile(target).sheet_names else ""),
            "offset": safe_offset,
            "limit": safe_limit,
            "returned_rows": len(sliced),
            "total_rows": len(frame),
            "columns": [str(item) for item in frame.columns.tolist()],
            "rows": json.loads(sliced.to_json(orient="records", force_ascii=False)),
        }

    if suffix in PDF_EXTENSIONS:
        from pypdf import PdfReader

        reader = PdfReader(str(target))
        start = safe_offset - 1
        end = min(len(reader.pages), start + safe_limit)
        chunks = []
        for index in range(start, end):
            chunks.append(reader.pages[index].extract_text() or "")
        content = "\n\n".join(chunk for chunk in chunks if chunk)
        return {
            "kind": "pdf",
            "filename": target.name,
            "path": str(target),
            "offset": safe_offset,
            "limit": safe_limit,
            "page_count": len(reader.pages),
            "returned_pages": max(0, end - start),
            "content": content,
        }

    lines = _read_text_file(target).splitlines()
    start = safe_offset - 1
    end = start + safe_limit
    selected = lines[start:end]
    return {
        "kind": kind,
        "filename": target.name,
        "path": str(target),
        "offset": safe_offset,
        "limit": safe_limit,
        "total_lines": len(lines),
        "returned_lines": len(selected),
        "content": "\n".join(selected),
    }
