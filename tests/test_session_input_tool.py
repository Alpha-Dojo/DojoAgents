from __future__ import annotations

from pathlib import Path
import io

import pytest
from PIL import Image

from dojoagents.agent.models import ToolCall
from dojoagents.dashboard.services.session_inputs import save_session_input_file
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.session_input_tool import get_read_session_input_spec
from dojoagents.tools.session_input_ingest import (
    SessionInputImageAnimatedError,
    SessionInputImageInvalidError,
    SessionInputImageTooLargeError,
    detect_session_input_kind,
    ingest_session_input_preview,
    inspect_session_input_image,
    read_session_input_slice,
)


@pytest.mark.asyncio
async def test_read_session_input_tool_reads_uploaded_file(tmp_path: Path) -> None:
    save_session_input_file(
        tmp_path,
        "sess-read",
        "memo.md",
        b"# Title\n\nBody text\n",
    )
    registry = ToolRegistry()
    registry.register(get_read_session_input_spec(tmp_path))
    executor = ToolExecutor(registry, SandboxPolicy())

    result = await executor.execute_one(
        ToolCall(id="call-read", name="read_session_input", arguments={"filename": "memo.md"}),
        session_id="sess-read",
    )

    assert result.ok is True
    assert "Body text" in result.content
    assert result.data["filename"] == "memo.md"


def test_image_session_input_is_metadata_not_binary_text(tmp_path: Path) -> None:
    target = tmp_path / "photo.png"
    output = io.BytesIO()
    Image.new("RGB", (3, 2), color="blue").save(output, format="PNG")
    target.write_bytes(output.getvalue())

    preview = ingest_session_input_preview(target)
    sliced = read_session_input_slice(target)

    assert detect_session_input_kind(target.name) == "image"
    assert preview["kind"] == "image"
    assert preview["content_type"] == "image/png"
    assert preview["preview_text"] == ""
    assert preview["width"] == 3
    assert sliced["kind"] == "image"
    assert "content" not in sliced


def test_image_session_input_rejects_animation_by_default(tmp_path: Path) -> None:
    target = tmp_path / "animated.gif"
    first = Image.new("RGB", (2, 2), color="red")
    second = Image.new("RGB", (2, 2), color="blue")
    first.save(target, format="GIF", save_all=True, append_images=[second], duration=20)

    with pytest.raises(SessionInputImageAnimatedError):
        inspect_session_input_image(target)


def test_image_session_input_enforces_pixel_limit(tmp_path: Path) -> None:
    target = tmp_path / "photo.png"
    Image.new("RGB", (3, 2), color="blue").save(target, format="PNG")

    with pytest.raises(SessionInputImageTooLargeError):
        inspect_session_input_image(target, max_pixels=5)


def test_image_session_input_rejects_damaged_payload(tmp_path: Path) -> None:
    target = tmp_path / "photo.png"
    target.write_bytes(b"not an image")

    with pytest.raises(SessionInputImageInvalidError):
        inspect_session_input_image(target)
