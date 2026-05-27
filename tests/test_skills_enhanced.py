from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
import yaml

from dojoagents.utils.fuzzy_match import fuzzy_find_and_replace
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.skill_manage import SkillManagerTool


def test_fuzzy_find_and_replace():
    # Strategy 1: Exact
    content = "def test():\n    return 42"
    new_c, count, strategy, err = fuzzy_find_and_replace(content, "return 42", "return 100")
    assert err is None
    assert count == 1
    assert strategy == "exact"
    assert new_c == "def test():\n    return 100"

    # Strategy 2: Line trimmed
    content = "def test():   \n    return 42   "
    new_c, count, strategy, err = fuzzy_find_and_replace(content, "def test():\nreturn 42", "def test():\n    return 100")
    assert err is None
    assert count == 1
    assert strategy == "line_trimmed"

    # Strategy 3: Whitespace normalized
    content = "def   test():\nreturn\t\t42"
    new_c, count, strategy, err = fuzzy_find_and_replace(content, "def test():\nreturn 42", "def test():\nreturn 100")
    assert err is None
    assert count == 1
    assert strategy == "whitespace_normalized"
    assert new_c == "def test():\nreturn 100"

    # Strategy 4: Indentation flexible
    content = "  def test():\n    return 42"
    new_c, count, strategy, err = fuzzy_find_and_replace(content, "def test():\nreturn 42", "def test():\n    return 100")
    assert err is None
    assert count == 1
    assert strategy in ("line_trimmed", "indentation_flexible")

    # replace_all uniqueness check
    content = "foo\nfoo"
    new_c, count, strategy, err = fuzzy_find_and_replace(content, "foo", "bar", replace_all=False)
    assert "Found 2 matches" in err

    new_c, count, strategy, err = fuzzy_find_and_replace(content, "foo", "bar", replace_all=True)
    assert err is None
    assert count == 2
    assert new_c == "bar\nbar"


def test_skill_manager_parsing_and_filtering(tmp_path):
    # Frontmatter parsing
    content = """---
name: my-skill
description: This is a description
platforms: [macos, linux]
requires_tools: [tool_a]
---
# Content of skill
"""
    fm, body = SkillManager.parse_frontmatter(content)
    assert fm["name"] == "my-skill"
    assert fm["description"] == "This is a description"
    assert fm["platforms"] == ["macos", "linux"]
    assert fm["requires_tools"] == ["tool_a"]
    assert "# Content of skill" in body

    # Skill Manager loading/filtering
    skill_a_dir = tmp_path / "skill-a"
    skill_a_dir.mkdir()
    (skill_a_dir / "SKILL.md").write_text(content, encoding="utf-8")

    # Platform matching check
    current_os = "macos" if sys.platform == "darwin" else ("linux" if sys.platform.startswith("linux") else "windows")
    content_compat = f"""---
name: skill-compat
description: desc
platforms: [{current_os}]
---
body
"""
    content_incompat = """---
name: skill-incompat
description: desc
platforms: [incompatible-os]
---
body
"""
    skill_compat_dir = tmp_path / "skill-compat"
    skill_compat_dir.mkdir()
    (skill_compat_dir / "SKILL.md").write_text(content_compat, encoding="utf-8")

    skill_incompat_dir = tmp_path / "skill-incompat"
    skill_incompat_dir.mkdir()
    (skill_incompat_dir / "SKILL.md").write_text(content_incompat, encoding="utf-8")

    manager = SkillManager(
        skill_dirs=[tmp_path],
        loaded_tools=["tool_a"],
    )

    skills = manager.list_skills()
    assert "skill-compat" in skills
    assert "skill-incompat" in skills
    
    prompt = manager.prompt_block()
    assert "skill-compat" in prompt
    assert "skill-incompat" not in prompt

    # Tool requirement checks
    content_tool_req = """---
name: skill-tool-req
description: desc
requires_tools: [missing_tool]
---
body
"""
    skill_tool_req_dir = tmp_path / "skill-tool-req"
    skill_tool_req_dir.mkdir()
    (skill_tool_req_dir / "SKILL.md").write_text(content_tool_req, encoding="utf-8")

    manager = SkillManager(
        skill_dirs=[tmp_path],
        loaded_tools=["tool_a"],
    )
    prompt = manager.prompt_block()
    assert "skill-tool-req" not in prompt

    # Disable filtering
    manager_disabled = SkillManager(
        skill_dirs=[tmp_path],
        disabled_skills=["skill-compat"],
    )
    assert "skill-compat" not in manager_disabled.list_skills()
    assert "skill-compat" not in manager_disabled.prompt_block()

    # Platform-specific disabling
    manager_platform = SkillManager(
        skill_dirs=[tmp_path],
        platform_disabled={"wechat": ["skill-compat"]},
    )
    assert "skill-compat" not in manager_platform.list_skills(platform="wechat")
    assert "skill-compat" not in manager_platform.prompt_block(platform="wechat")
    assert "skill-compat" in manager_platform.list_skills(platform="cli")
    assert "skill-compat" in manager_platform.prompt_block(platform="cli")


@pytest.mark.asyncio
async def test_skill_manager_tool_crud(tmp_path):
    manager = SkillManager(skill_dirs=[tmp_path])
    tool = SkillManagerTool(main_skills_dir=tmp_path, skill_manager=manager)
    spec = tool.get_tool_spec()
    assert spec.name == "skill_manage"

    # Create Skill
    content = """---
name: test-skill
description: description of test-skill
---
# Test Skill
This is the procedure.
"""
    res = await spec.handler({
        "action": "create",
        "name": "test-skill",
        "content": content
    })
    assert res["metadata"]["ok"] is True
    assert (tmp_path / "test-skill" / "SKILL.md").exists()

    # List Skills
    res = await spec.handler({
        "action": "list"
    })
    assert res["metadata"]["ok"] is True
    assert "test-skill" in res["metadata"]["skills"]

    # Edit Skill
    new_content = """---
name: test-skill
description: updated description
---
# Test Skill
Updated procedure.
"""
    res = await spec.handler({
        "action": "edit",
        "name": "test-skill",
        "content": new_content
    })
    assert res["metadata"]["ok"] is True
    assert "updated description" in (tmp_path / "test-skill" / "SKILL.md").read_text(encoding="utf-8")

    # Patch Skill
    res = await spec.handler({
        "action": "patch",
        "name": "test-skill",
        "old_string": "Updated procedure.",
        "new_string": "Patched procedure."
    })
    assert res["metadata"]["ok"] is True
    assert "Patched procedure." in (tmp_path / "test-skill" / "SKILL.md").read_text(encoding="utf-8")

    # Write subfile
    res = await spec.handler({
        "action": "write_file",
        "name": "test-skill",
        "file_path": "references/guide.md",
        "file_content": "This is a reference guide."
    })
    assert res["metadata"]["ok"] is True
    assert (tmp_path / "test-skill" / "references" / "guide.md").exists()

    # Write subfile invalid directory check
    res = await spec.handler({
        "action": "write_file",
        "name": "test-skill",
        "file_path": "invalid_dir/guide.md",
        "file_content": "This is a reference guide."
    })
    assert res["metadata"]["ok"] is False

    # Path traversal check
    res = await spec.handler({
        "action": "write_file",
        "name": "test-skill",
        "file_path": "references/../../guide.md",
        "file_content": "This is a reference guide."
    })
    assert res["metadata"]["ok"] is False

    # Remove subfile
    res = await spec.handler({
        "action": "remove_file",
        "name": "test-skill",
        "file_path": "references/guide.md"
    })
    assert res["metadata"]["ok"] is True
    assert not (tmp_path / "test-skill" / "references" / "guide.md").exists()

    # Delete Skill
    res = await spec.handler({
        "action": "delete",
        "name": "test-skill"
    })
    assert res["metadata"]["ok"] is True
    assert not (tmp_path / "test-skill").exists()
