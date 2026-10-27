from __future__ import annotations

import re
from pathlib import Path

import pytest

from dojoagents.memory.local_memory import LocalMemoryProvider
from dojoagents.memory.skill_summary import (
    GENERATED_SKILL_NAME_MAX_LENGTH,
    SESSION_HASH_LENGTH,
    SkillSummaryMemoryProvider,
)


def test_short_session_id_keeps_legacy_generated_skill_name() -> None:
    assert SkillSummaryMemoryProvider._generated_skill_name("Session-123") == (
        "generated-session-123"
    )


def test_long_session_id_name_is_bounded_stable_and_hashed() -> None:
    session_id = "market-research-" + ("a" * 300)

    first = SkillSummaryMemoryProvider._generated_skill_name(session_id)
    second = SkillSummaryMemoryProvider._generated_skill_name(session_id)

    assert first == second
    assert len(first) <= GENERATED_SKILL_NAME_MAX_LENGTH
    assert re.fullmatch(rf"generated-[a-z0-9._-]+-[0-9a-f]{{{SESSION_HASH_LENGTH}}}", first)


def test_long_session_ids_with_same_prefix_do_not_collide() -> None:
    common_prefix = "same-prefix-" + ("x" * 300)

    first = SkillSummaryMemoryProvider._generated_skill_name(common_prefix + "-one")
    second = SkillSummaryMemoryProvider._generated_skill_name(common_prefix + "-two")

    assert first != second
    assert len(first) <= GENERATED_SKILL_NAME_MAX_LENGTH
    assert len(second) <= GENERATED_SKILL_NAME_MAX_LENGTH


@pytest.mark.parametrize(
    "session_id",
    [
        "../../outside/skill",
        "中文 会话 / 特殊字符 ? *",
        "   ",
    ],
)
def test_generated_skill_name_is_one_safe_path_component(session_id: str) -> None:
    name = SkillSummaryMemoryProvider._generated_skill_name(session_id)

    assert name not in {"", ".", ".."}
    assert Path(name).name == name
    assert "/" not in name
    assert "\\" not in name


@pytest.mark.anyio
async def test_long_session_writes_matching_directory_and_frontmatter(tmp_path: Path) -> None:
    provider = SkillSummaryMemoryProvider(tmp_path)
    session_id = "analysis-" + ("z" * 300)
    await provider.initialize(session_id)

    await provider.on_session_end(
        [
            {"role": "user", "content": "Analyze the market"},
            {"role": "assistant", "content": "Completed"},
        ]
    )

    skill_name = provider._generated_skill_name(session_id)
    skill_file = tmp_path / skill_name / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    assert skill_file.is_file()
    assert len(skill_file.parent.name) <= GENERATED_SKILL_NAME_MAX_LENGTH
    assert f"\nname: {skill_file.parent.name}\n" in content
    assert "Analyze the market\nCompleted" in content
    assert not list(skill_file.parent.glob(".SKILL.md.*.tmp"))


@pytest.mark.anyio
async def test_empty_summary_does_not_create_generated_skill(tmp_path: Path) -> None:
    provider = SkillSummaryMemoryProvider(tmp_path)
    await provider.initialize("empty-session")

    await provider.on_session_end([{"content": "   "}])

    assert list(tmp_path.iterdir()) == []


@pytest.mark.anyio
async def test_local_memory_uses_safe_bounded_name_and_round_trips(tmp_path: Path) -> None:
    provider = LocalMemoryProvider(tmp_path)
    session_id = "../../outside/" + ("long-session-" * 40)
    await provider.initialize(session_id)

    await provider.save_memory(session_id, "persistent summary")

    memory_file = provider._memory_file(session_id)
    assert memory_file.parent == tmp_path
    assert memory_file.is_file()
    assert len(memory_file.name) <= GENERATED_SKILL_NAME_MAX_LENGTH
    assert await provider.retrieve_memory(session_id, "ignored") == "persistent summary"
    assert await provider.prefetch("ignored", session_id=session_id) == (
        "[CONSOLIDATED MEMORY FROM PREVIOUS TURNS]:\npersistent summary"
    )
    assert not list(tmp_path.glob(".session_*.tmp"))


@pytest.mark.anyio
async def test_local_memory_short_safe_name_remains_compatible(tmp_path: Path) -> None:
    provider = LocalMemoryProvider(tmp_path)
    await provider.initialize("session-123")

    await provider.save_memory("session-123", "summary")

    assert provider._memory_file("session-123") == tmp_path / "session_session-123.txt"
