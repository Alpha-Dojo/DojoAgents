from __future__ import annotations

import base64
import re
from typing import Any

_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", re.DOTALL)

IMAGE_TURN_EXCLUDED_TOOLS = frozenset(
    {
        "terminal",
        "code_execution",
        "execute_code",
        "write_file",
        "patch",
    }
)

MULTIMODAL_IMAGE_PROTOCOL = """
## Attached Images

The user attached one or more images in this turn. The image bytes are already in the model context.

- Read and answer from the attached image(s) directly. Treat this as a vision task.
- Do NOT call terminal, code_execution, execute_code, or similar tools to OCR, download, convert, or process the image.
- Do NOT claim the image is missing when image parts are present in the user message.
- If the image is unclear, describe what you can see and ask one focused follow-up question.
""".strip()

_OPENAI_IMAGE_FORMATS = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/gif": "gif",
    "image/webp": "webp",
}


def parse_data_image_url(url: str) -> tuple[str, bytes] | None:
    match = _DATA_URL_RE.match(str(url or "").strip())
    if not match:
        return None
    mime = match.group(1).lower()
    image_format = _OPENAI_IMAGE_FORMATS.get(mime)
    if image_format is None:
        return None
    try:
        payload = base64.b64decode(match.group(2), validate=True)
    except (ValueError, TypeError):
        return None
    if not payload:
        return None
    return image_format, payload


def openai_image_url_to_strands_block(url: str) -> dict[str, Any] | None:
    parsed = parse_data_image_url(url)
    if parsed is None:
        stripped = str(url or "").strip()
        if not stripped:
            return None
        return {
            "image": {
                "format": "png",
                "source": {"location": {"type": stripped}},
            }
        }
    image_format, payload = parsed
    return {
        "image": {
            "format": image_format,
            "source": {"bytes": payload},
        }
    }


def openai_content_to_strands_blocks(content: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if content is None:
        return []
    if isinstance(content, str):
        text = content.strip()
        return [{"text": text}] if text else []
    blocks: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            text = str(part.get("text") or "").strip()
            if text:
                blocks.append({"text": text})
            continue
        if part_type == "image_url":
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            image_block = openai_image_url_to_strands_block(str(url or ""))
            if image_block is not None:
                blocks.append(image_block)
    return blocks


def strands_image_block_to_openai_part(block: dict[str, Any]) -> dict[str, Any] | None:
    image = block.get("image")
    if not isinstance(image, dict):
        return None
    source = image.get("source")
    if not isinstance(source, dict):
        return None
    image_format = str(image.get("format") or "png")
    raw_bytes = source.get("bytes")
    if raw_bytes is not None:
        if isinstance(raw_bytes, str):
            encoded = raw_bytes
        else:
            encoded = base64.b64encode(raw_bytes).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/{image_format};base64,{encoded}"},
        }
    location = source.get("location")
    if isinstance(location, dict):
        url = str(location.get("type") or "").strip()
        if url:
            return {"type": "image_url", "image_url": {"url": url}}
    return None


def normalize_openai_message_content(content: Any) -> str | list[dict[str, Any]]:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            text = str(part.get("text") or "")
            if text:
                parts.append({"type": "text", "text": text})
            continue
        if part_type == "image_url":
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            url_text = str(url or "").strip()
            if url_text:
                parts.append({"type": "image_url", "image_url": {"url": url_text}})
    if not parts:
        return ""
    if len(parts) == 1 and parts[0].get("type") == "text":
        return str(parts[0].get("text") or "")
    return parts


def openai_content_to_gemini_parts(content: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if content is None:
        return []
    if isinstance(content, str):
        text = content.strip()
        return [{"text": text}] if text else []
    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            text = str(part.get("text") or "").strip()
            if text:
                parts.append({"text": text})
            continue
        if part_type == "image_url":
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            parsed = parse_data_image_url(str(url or ""))
            if parsed is None:
                continue
            image_format, payload = parsed
            parts.append(
                {
                    "inline_data": {
                        "mime_type": f"image/{image_format}",
                        "data": base64.b64encode(payload).decode("ascii"),
                    }
                }
            )
    return parts


def openai_content_has_images(content: str | list[dict[str, Any]] | None) -> bool:
    if content is None:
        return False
    if isinstance(content, str):
        return False
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "image_url":
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if str(url or "").strip():
                return True
    return False


def openai_content_has_payload(content: str | list[dict[str, Any]] | None) -> bool:
    return openai_content_has_images(content) or bool(openai_content_text(content))


def openai_content_text(content: str | list[dict[str, Any]] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    text_parts: list[str] = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            text_parts.append(str(part.get("text") or ""))
    return "".join(text_parts).strip()


def openai_user_message_to_dojo(content: str | list[dict[str, Any]] | None) -> dict[str, Any] | None:
    normalized = normalize_openai_message_content(content)
    if not openai_content_has_payload(normalized):
        return None
    if isinstance(normalized, str):
        return {"role": "user", "content": normalized}
    return {"role": "user", "content": normalized}
