from __future__ import annotations

from pathlib import Path

import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.dashboard.services.session_inputs import save_session_input_file
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.session_input_tool import get_read_session_input_spec


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
