from __future__ import annotations

import json
from pathlib import Path
import pytest
from dojoagents.skills.manager import SkillManager
from dojoagents.skills.cache import SkillPromptCache
from dojoagents.tools.skill_manage import SkillsListTool, SkillViewTool


def test_skill_prompt_cache(tmp_path):
    cache_file = tmp_path / ".skills_cache.json"
    cache = SkillPromptCache(cache_file)

    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(
        "---\nname: test\ncategory: math\ndescription: math guide\n---\nbody text",
        encoding="utf-8",
    )

    # Get empty cache
    res = cache.get(skill_file)
    assert res is None

    # Set cache
    fm = {"name": "test", "category": "math", "description": "math guide"}
    body = "body text"
    cache.set(skill_file, fm, body)

    # Get from cache
    cached = cache.get(skill_file)
    assert cached is not None
    assert cached[0] == fm
    assert cached[1] == body

    # Modify file, mtime/size should change, cache should invalidate
    skill_file.write_text(
        "---\nname: test\ncategory: math\ndescription: math guide\n---\nbody text modified",
        encoding="utf-8",
    )
    assert cache.get(skill_file) is None


def test_skill_manager_lazy_skills(tmp_path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ncategory: science\ndescription: science helper\n---\nscience guidelines",
        encoding="utf-8",
    )

    # Test with lazy_skills=True
    manager = SkillManager(
        skill_dirs=[tmp_path], enable_cache=True, lazy_skills=True
    )
    prompt = manager.prompt_block()
    assert "Available Skills (Mandatory Lazy Loader)" in prompt
    assert "science helper" in prompt
    assert "science guidelines" not in prompt

    # Test with lazy_skills=False
    manager_full = SkillManager(
        skill_dirs=[tmp_path], enable_cache=True, lazy_skills=False
    )
    prompt_full = manager_full.prompt_block()
    assert "Available Skills (Mandatory Lazy Loader)" not in prompt_full
    assert "science guidelines" in prompt_full


@pytest.mark.asyncio
async def test_skills_list_and_view_tools(tmp_path):
    skill_dir = tmp_path / "math-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: math-skill\ncategory: calc\ndescription: integration guide\n---\nuse integral formula",
        encoding="utf-8",
    )

    manager = SkillManager(
        skill_dirs=[tmp_path], enable_cache=True, lazy_skills=True
    )

    list_tool = SkillsListTool(manager)
    list_spec = list_tool.get_tool_spec()
    assert list_spec.name == "skills_list"
    res_list = await list_spec.handler({})
    assert res_list["metadata"]["ok"] is True
    skills = json.loads(res_list["content"])
    assert len(skills) == 1
    assert skills[0]["name"] == "math-skill"
    assert skills[0]["category"] == "calc"
    assert skills[0]["description"] == "integration guide"

    view_tool = SkillViewTool(manager)
    view_spec = view_tool.get_tool_spec()
    assert view_spec.name == "skill_view"

    # Successful view
    res_view = await view_spec.handler({"name": "math-skill"})
    assert res_view["metadata"]["ok"] is True
    assert "use integral formula" in res_view["content"]

    # Non-existent view
    res_view_fail = await view_spec.handler({"name": "non-existent"})
    assert res_view_fail["metadata"]["ok"] is False
    assert "not found" in res_view_fail["content"]
