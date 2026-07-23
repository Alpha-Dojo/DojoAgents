from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
import yaml

from dojoagents.tools.registry import ToolSpec
from dojoagents.utils.fuzzy_match import fuzzy_find_and_replace
from dojoagents.skills.manager import SkillManager

ALLOWED_SUBDIRS = {"references", "scripts", "templates", "assets"}
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024


class SkillManagerTool:
    def __init__(self, main_skills_dir: Path, skill_manager: SkillManager) -> None:
        self.main_skills_dir = Path(main_skills_dir).expanduser()
        self.skill_manager = skill_manager

    def get_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name="skill_manage",
            description=(
                "Manage agent skills (list, create, edit, patch, delete, write_file, remove_file). "
                "Skills are procedural memory guidelines that teach you how to perform specific analysis workflows."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "create", "edit", "patch", "delete", "write_file", "remove_file"], "description": "Action to perform."},
                    "name": {
                        "type": "string",
                        "description": "Skill name (lowercase, hyphens/underscores allowed, e.g., 'stock-trend-analysis'). Required for all actions except 'list'.",
                    },
                    "content": {"type": "string", "description": "Full SKILL.md content (YAML frontmatter + markdown body). Required for 'create' and 'edit'."},
                    "file_path": {"type": "string", "description": "Subfile path under references/, scripts/, templates/, or assets/. Required for write_file/remove_file."},
                    "file_content": {"type": "string", "description": "Content of the supporting file. Required for write_file."},
                    "old_string": {"type": "string", "description": "The exact or close text to match in patch action."},
                    "new_string": {"type": "string", "description": "Replacement text in patch action."},
                    "replace_all": {"type": "boolean", "description": "For 'patch': replace all occurrences instead of requiring a unique match (default: false)."},
                },
                "required": ["action"],
            },
            handler=self.handle_call,
        )

    async def handle_call(self, args: dict[str, Any]) -> dict[str, Any]:
        action = args.get("action")

        if action == "list":
            try:
                skills = self.skill_manager.list_skills()
                if not skills:
                    return {"content": "No active skills found in the system.", "metadata": {"ok": True, "skills": []}}
                skills_list_str = ", ".join(skills)
                return {"content": f"Currently available skills: {skills_list_str}", "metadata": {"ok": True, "skills": skills}}
            except Exception as e:
                return {"content": f"Failed to list skills: {e}", "metadata": {"ok": False}}

        name = args.get("name", "").strip()

        if not name:
            return {"content": "Skill name is required.", "metadata": {"ok": False}}

        if len(name) > MAX_NAME_LENGTH:
            return {"content": f"Skill name exceeds {MAX_NAME_LENGTH} characters.", "metadata": {"ok": False}}

        if not re.match(r"^[a-z0-9][a-z0-9._-]*$", name):
            return {"content": f"Invalid skill name '{name}'. Use lowercase letters, numbers, hyphens, dots, and underscores.", "metadata": {"ok": False}}

        skill_dir = self.main_skills_dir / name
        skill_md = skill_dir / "SKILL.md"

        try:
            if action == "create":
                content = args.get("content", "")
                if not content.strip():
                    return {"content": "content is required for action='create'", "metadata": {"ok": False}}

                # Validate frontmatter
                if not content.startswith("---"):
                    return {"content": "SKILL.md must start with YAML frontmatter (---).", "metadata": {"ok": False}}

                end_match = re.search(r"\n---\s*\n", content[3:])
                if not end_match:
                    return {"content": "SKILL.md frontmatter is not closed.", "metadata": {"ok": False}}

                yaml_content = content[3 : end_match.start() + 3]
                try:
                    parsed = yaml.safe_load(yaml_content)
                except Exception as e:
                    return {"content": f"YAML frontmatter parse error: {e}", "metadata": {"ok": False}}

                if not isinstance(parsed, dict):
                    return {"content": "Frontmatter must be a YAML mapping.", "metadata": {"ok": False}}

                if "name" not in parsed:
                    return {"content": "Frontmatter must include 'name' field.", "metadata": {"ok": False}}
                if "description" not in parsed:
                    return {"content": "Frontmatter must include 'description' field.", "metadata": {"ok": False}}

                if len(str(parsed["description"])) > MAX_DESCRIPTION_LENGTH:
                    return {"content": f"Description exceeds {MAX_DESCRIPTION_LENGTH} characters.", "metadata": {"ok": False}}

                if skill_md.exists():
                    return {"content": f"A skill named '{name}' already exists.", "metadata": {"ok": False}}

                skill_dir.mkdir(parents=True, exist_ok=True)
                self._atomic_write(skill_md, content)
                return {"content": f"Skill '{name}' created successfully.", "metadata": {"ok": True}}

            elif action == "edit":
                content = args.get("content", "")
                if not content.strip():
                    return {"content": "content is required for action='edit'", "metadata": {"ok": False}}

                # Validate frontmatter
                if not content.startswith("---"):
                    return {"content": "SKILL.md must start with YAML frontmatter (---).", "metadata": {"ok": False}}

                end_match = re.search(r"\n---\s*\n", content[3:])
                if not end_match:
                    return {"content": "SKILL.md frontmatter is not closed.", "metadata": {"ok": False}}

                if not skill_md.exists():
                    return {"content": f"Skill '{name}' does not exist.", "metadata": {"ok": False}}

                self._atomic_write(skill_md, content)
                return {"content": f"Skill '{name}' updated successfully.", "metadata": {"ok": True}}

            elif action == "patch":
                old_string = args.get("old_string")
                new_string = args.get("new_string")
                file_path = args.get("file_path", "SKILL.md")
                replace_all = bool(args.get("replace_all", False))

                if old_string is None:
                    return {"content": "old_string is required for patch.", "metadata": {"ok": False}}
                if new_string is None:
                    return {"content": "new_string is required for patch.", "metadata": {"ok": False}}

                target_file = skill_dir / file_path
                if not target_file.exists():
                    return {"content": f"File '{file_path}' in skill '{name}' does not exist.", "metadata": {"ok": False}}

                # Security check
                err = self._validate_subdir(file_path) if file_path != "SKILL.md" else None
                if err:
                    return {"content": err, "metadata": {"ok": False}}

                orig_text = target_file.read_text(encoding="utf-8")
                new_content, match_count, strategy, error = fuzzy_find_and_replace(orig_text, old_string, new_string, replace_all)
                if error:
                    return {"content": f"Patch failed: {error}", "metadata": {"ok": False}}

                # If patching SKILL.md, ensure frontmatter validity
                if file_path == "SKILL.md":
                    if not new_content.startswith("---") or not re.search(r"\n---\s*\n", new_content[3:]):
                        return {"content": "Patch would break SKILL.md frontmatter structure.", "metadata": {"ok": False}}

                self._atomic_write(target_file, new_content)
                return {"content": f"Patched '{file_path}' in skill '{name}' ({match_count} replacement(s) using strategy '{strategy}').", "metadata": {"ok": True}}

            elif action == "delete":
                if not skill_dir.exists():
                    return {"content": f"Skill '{name}' does not exist.", "metadata": {"ok": False}}

                shutil.rmtree(skill_dir)
                return {"content": f"Skill '{name}' deleted successfully.", "metadata": {"ok": True}}

            elif action == "write_file":
                file_path = args.get("file_path", "")
                file_content = args.get("file_content")

                err = self._validate_subdir(file_path)
                if err:
                    return {"content": err, "metadata": {"ok": False}}
                if file_content is None:
                    return {"content": "file_content is required for write_file.", "metadata": {"ok": False}}

                target_file = skill_dir / file_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                self._atomic_write(target_file, file_content)
                return {"content": f"File '{file_path}' written to skill '{name}'.", "metadata": {"ok": True}}

            elif action == "remove_file":
                file_path = args.get("file_path", "")
                err = self._validate_subdir(file_path)
                if err:
                    return {"content": err, "metadata": {"ok": False}}

                target_file = skill_dir / file_path
                if not target_file.exists():
                    return {"content": f"File '{file_path}' not found in skill '{name}'.", "metadata": {"ok": False}}

                target_file.unlink()
                if not any(target_file.parent.iterdir()):
                    target_file.parent.rmdir()
                return {"content": f"File '{file_path}' removed from skill '{name}'.", "metadata": {"ok": True}}

            else:
                return {"content": f"Unknown action '{action}'.", "metadata": {"ok": False}}

        except Exception as e:
            return {"content": f"Unexpected skill manager error: {e}", "metadata": {"ok": False}}

    def _atomic_write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tf:
            tf.write(text)
            temp_name = tf.name
        Path(temp_name).replace(path)

    def _validate_subdir(self, file_path: str) -> str | None:
        if not file_path:
            return "file_path is required"
        normalized = Path(file_path)
        if not normalized.parts or normalized.parts[0] not in ALLOWED_SUBDIRS:
            return f"Supporting files must reside in one of: {', '.join(ALLOWED_SUBDIRS)}"
        if ".." in normalized.parts:
            return "Path traversal ('..') is not allowed."
        return None


class SkillsListTool:
    def __init__(self, skill_manager: SkillManager) -> None:
        self.skill_manager = skill_manager

    def get_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name="skills_list",
            description="List all available skills (names, categories, and descriptions).",
            parameters={
                "type": "object",
                "properties": {},
            },
            handler=self.handle_call,
        )

    async def handle_call(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            skills_data = []
            seen_skills = set()
            for root in self.skill_manager.skill_dirs:
                if not root.exists():
                    continue
                for skill_file in sorted(root.glob("*/SKILL.md")):
                    skill_name = skill_file.parent.name
                    if skill_name in self.skill_manager.disabled_skills or skill_name in seen_skills:
                        continue
                    try:
                        frontmatter, body = self.skill_manager._get_skill_content(skill_file)
                        if not self.skill_manager._matches_platform(frontmatter):
                            continue
                        if not self.skill_manager._matches_tool_requirements(frontmatter):
                            continue
                        seen_skills.add(skill_name)
                        skills_data.append(
                            {"name": skill_name, "category": frontmatter.get("category", "general"), "description": frontmatter.get("description", "No description provided.")}
                        )
                    except Exception:
                        continue

            return {"content": json.dumps(skills_data, indent=2, ensure_ascii=False), "metadata": {"ok": True}}
        except Exception as e:
            return {"content": f"Failed to list skills: {e}", "metadata": {"ok": False}}


class SkillViewTool:
    def __init__(self, skill_manager: SkillManager) -> None:
        self.skill_manager = skill_manager

    def get_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            name="skill_view",
            description="View the detailed instructions and documentation of a specific skill by name.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "The exact name of the skill to view (e.g. 'dojo-quant-analyst')."}},
                "required": ["name"],
            },
            handler=self.handle_call,
        )

    async def handle_call(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("name", "").strip()
        if not name:
            return {"content": "Skill name is required.", "metadata": {"ok": False}}

        try:
            for root in self.skill_manager.skill_dirs:
                if not root.exists():
                    continue
                skill_file = root / name / "SKILL.md"
                if skill_file.exists():
                    frontmatter, body = self.skill_manager._get_skill_content(skill_file)
                    content = skill_file.read_text(encoding="utf-8")
                    return {"content": content, "metadata": {"ok": True}}
            return {"content": f"Skill '{name}' not found.", "metadata": {"ok": False}}
        except Exception as e:
            return {"content": f"Failed to view skill: {e}", "metadata": {"ok": False}}
