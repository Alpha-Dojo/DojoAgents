from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Tuple, Dict
import yaml

PLATFORM_MAP = {
    "macos": "darwin",
    "linux": "linux",
    "windows": "win32",
}

class SkillManager:
    def __init__(
        self,
        skill_dirs: list[str | Path] | None = None,
        disabled_skills: list[str] | None = None,
        platform_disabled: dict[str, list[str]] | None = None,
        loaded_tools: list[str] | None = None,
        enable_cache: bool = True,
        lazy_skills: bool = True,
    ) -> None:
        self.skill_dirs = [Path(path).expanduser() for path in (skill_dirs or [])]
        self.disabled_skills = set(disabled_skills or [])
        self.platform_disabled = platform_disabled or {}
        self.loaded_tools = set(loaded_tools or [])
        self.enable_cache = enable_cache
        self.lazy_skills = lazy_skills
        self.cache = None
        if enable_cache and self.skill_dirs:
            from dojoagents.skills.cache import SkillPromptCache
            cache_file = self.skill_dirs[0] / ".skills_cache.json"
            self.cache = SkillPromptCache(cache_file)

    @staticmethod
    def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
        """Parses the YAML frontmatter from a markdown string."""
        frontmatter: Dict[str, Any] = {}
        body = content
        if not content.strip().startswith("---"):
            return frontmatter, body

        # Find the closing boundary
        end_match = re.search(r"\n---\s*\n", content[3:])
        if not end_match:
            return frontmatter, body

        yaml_content = content[3 : end_match.start() + 3]
        body = content[end_match.end() + 3 :]
        try:
            parsed = yaml.safe_load(yaml_content)
            if isinstance(parsed, dict):
                frontmatter = parsed
        except Exception:
            # Fallback simple line parsing for robustness
            for line in yaml_content.strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    frontmatter[k.strip()] = v.strip()
        return frontmatter, body

    def _matches_platform(self, frontmatter: Dict[str, Any]) -> bool:
        """Returns True if the skill supports the current operating system."""
        platforms = frontmatter.get("platforms")
        if not platforms:
            return True
        if not isinstance(platforms, list):
            platforms = [platforms]
        current = sys.platform
        for p in platforms:
            normalized = str(p).lower().strip()
            mapped = PLATFORM_MAP.get(normalized, normalized)
            if current.startswith(mapped):
                return True
        return False

    def _matches_tool_requirements(self, frontmatter: Dict[str, Any]) -> bool:
        """Returns True if all required tools for the skill are loaded in the agent."""
        req_tools = frontmatter.get("requires_tools")
        if not req_tools:
            return True
        if not isinstance(req_tools, list):
            req_tools = [req_tools]
        return all(t in self.loaded_tools for t in req_tools)

    def _get_skill_content(self, skill_file: Path) -> tuple[dict[str, Any], str]:
        if self.enable_cache and self.cache:
            cached = self.cache.get(skill_file)
            if cached is not None:
                return cached

        content = skill_file.read_text(encoding="utf-8")
        frontmatter, body = self.parse_frontmatter(content)
        if self.enable_cache and self.cache:
            self.cache.set(skill_file, frontmatter, body)
        return frontmatter, body

    def prompt_block(self, platform: str | None = None) -> str:
        """Builds a concatenated text block or a catalog list of all valid, active skills."""
        active_disabled = set(self.disabled_skills)
        if platform and platform in self.platform_disabled:
            active_disabled.update(self.platform_disabled[platform])

        seen_skills: set[str] = set()
        skills_data: list[tuple[str, dict[str, Any], str]] = []

        for root in self.skill_dirs:
            if not root.exists():
                continue
            for skill_file in sorted(root.glob("*/SKILL.md")):
                skill_name = skill_file.parent.name
                if skill_name in active_disabled or skill_name in seen_skills:
                    continue

                try:
                    frontmatter, body = self._get_skill_content(skill_file)

                    # Apply platform and tool requirement checks
                    if not self._matches_platform(frontmatter):
                        continue
                    if not self._matches_tool_requirements(frontmatter):
                        continue

                    seen_skills.add(skill_name)
                    skills_data.append((skill_name, frontmatter, body))
                except Exception:
                    continue

        if self.lazy_skills:
            if not skills_data:
                return ""
            lines = [
                "## Available Skills (Mandatory Lazy Loader)",
                "You have access to the following skills. Do NOT guess their instructions.",
                "You MUST call `skill_view(name='<skill_name>')` to load the full skill instructions before performing any workflow related to these skills.",
                "To list all available skills, you can also use `skills_list()`.",
                "",
                "Skill Catalog:"
            ]
            categories: dict[str, list[dict]] = {}
            for name, fm, _ in skills_data:
                cat = fm.get("category", "general")
                desc = fm.get("description", "No description provided.")
                categories.setdefault(cat, []).append({"name": name, "description": desc})

            for cat, items in sorted(categories.items()):
                lines.append(f"  Category: {cat}")
                for item in items:
                    lines.append(f"    - {item['name']}: {item['description']}")
            return "\n".join(lines)
        else:
            full_blocks = []
            for name, fm, body in skills_data:
                if fm:
                    fm_str = yaml.dump(fm, default_flow_style=False) if hasattr(yaml, "dump") else str(fm)
                    full_blocks.append(f"---\n{fm_str}---\n{body}")
                else:
                    full_blocks.append(body)
            return "\n\n".join(full_blocks)

    def list_skills(self, platform: str | None = None) -> list[str]:
        """Lists names of all available, non-disabled skills."""
        active_disabled = set(self.disabled_skills)
        if platform and platform in self.platform_disabled:
            active_disabled.update(self.platform_disabled[platform])

        names: list[str] = []
        for root in self.skill_dirs:
            if root.exists():
                names.extend(path.parent.name for path in sorted(root.glob("*/SKILL.md")))
        return [n for n in names if n not in active_disabled]
