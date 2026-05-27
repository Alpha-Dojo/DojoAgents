from __future__ import annotations

from dojoagents.agent.runtime import Runtime

def test_built_in_skills_loaded():
    runtime = Runtime.from_default_config()
    skills = runtime.agent.skill_manager.list_skills()
    assert "writing-plans" in skills
    assert "plan" in skills
    assert "subagent-driven-development" in skills
