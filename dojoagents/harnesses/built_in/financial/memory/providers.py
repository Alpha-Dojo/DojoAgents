"""FinancialHarness memory provider selection."""

from pathlib import Path

from dojoagents.memory.skill_summary import SkillSummaryMemoryProvider


def create_skill_summary_provider(generated_skill_dir: str | Path) -> SkillSummaryMemoryProvider:
    return SkillSummaryMemoryProvider(generated_skill_dir)


__all__ = ["create_skill_summary_provider"]
