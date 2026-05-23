from __future__ import annotations

from dojoagents.skills.manager import SkillManager


def load_prompt_block(manager: SkillManager) -> str:
    return manager.prompt_block()
