from __future__ import annotations

from pathlib import Path


class SkillManager:
    def __init__(self, skill_dirs: list[str | Path] | None = None) -> None:
        self.skill_dirs = [Path(path).expanduser() for path in (skill_dirs or [])]

    def prompt_block(self) -> str:
        blocks: list[str] = []
        for root in self.skill_dirs:
            if not root.exists():
                continue
            for skill in sorted(root.glob("*/SKILL.md")):
                blocks.append(skill.read_text(encoding="utf-8"))
        return "\n\n".join(blocks)

    def list_skills(self) -> list[str]:
        names: list[str] = []
        for root in self.skill_dirs:
            if root.exists():
                names.extend(path.parent.name for path in sorted(root.glob("*/SKILL.md")))
        return names
