"""Resolution of configured supplemental harness sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dojoagents.skills.manager import SkillManager

from .errors import CapabilityConflictError


@dataclass(frozen=True)
class SkillSourceResolution:
    directories: tuple[Path, ...]
    disabled_skills: frozenset[str]
    warnings: tuple[str, ...]


def _skill_files(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(sorted(root.glob("*/SKILL.md")))


def resolve_extra_skill_sources(
    harness_dirs: Iterable[str | Path],
    extra_dirs: Iterable[str | Path],
    *,
    loaded_tools: set[str] | frozenset[str],
) -> SkillSourceResolution:
    """Order skill roots while enforcing Harness ownership and tool requirements."""

    harness_roots = tuple(Path(path).expanduser().resolve() for path in harness_dirs)
    extra_roots = tuple(Path(path).expanduser().resolve() for path in extra_dirs)
    harness_skills: dict[str, Path] = {}
    warnings: list[str] = []
    disabled: set[str] = set()
    for root in harness_roots:
        for skill_file in _skill_files(root):
            name = skill_file.parent.name
            existing = harness_skills.get(name)
            if existing is not None:
                raise CapabilityConflictError(f"duplicate Harness skill '{name}' from {existing} conflicts with {skill_file}")
            harness_skills[name] = skill_file

    seen_extra: set[str] = set()
    for root in extra_roots:
        for skill_file in _skill_files(root):
            name = skill_file.parent.name
            if name in harness_skills:
                warnings.append(f"extra skill '{name}' disabled because Harness owns the same skill")
                continue
            if name in seen_extra:
                warnings.append(f"duplicate extra skill '{name}' disabled after its first declaration")
                continue
            seen_extra.add(name)
            frontmatter, _ = SkillManager.parse_frontmatter(skill_file.read_text(encoding="utf-8"))
            required = frontmatter.get("requires_tools", ())
            if isinstance(required, str):
                required = (required,)
            missing = sorted(set(required).difference(loaded_tools))
            if missing:
                disabled.add(name)
                warnings.append(f"extra skill '{name}' disabled; missing tools: {', '.join(missing)}")

    return SkillSourceResolution(
        directories=harness_roots + extra_roots,
        disabled_skills=frozenset(disabled),
        warnings=tuple(warnings),
    )
