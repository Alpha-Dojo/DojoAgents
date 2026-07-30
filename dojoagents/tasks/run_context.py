"""Unified execution profile for prompt packs, tool allowlists, and completion.

Channel (dashboard/cli/scheduler) is transport. Trigger is how the run started.
Profile is the behavioral contract prompt/authorize/completion layers must share.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from dojoagents.agent.models import ChatRequest
from dojoagents.tasks.models import ActiveTask, PipelineState

PROFILE_FREEFORM = "freeform"
PROFILE_TASK_CONTRACT = "task_contract"
PROFILE_PIPELINE_STEP = "pipeline_step"
PROFILE_JOB_FREEFORM = "job_freeform"
PROFILE_JOB_TASK = "job_task"
PROFILE_SKILL_GUIDED = "skill_guided"
PROFILE_PLAN = "plan"

TRIGGER_USER_CHAT = "user_chat"
TRIGGER_TASK_COMMAND = "task_command"
TRIGGER_PIPELINE = "pipeline"
TRIGGER_CRON = "cron"
TRIGGER_SKILL = "skill"
TRIGGER_PLAN = "plan"

PACK_DASHBOARD_PROTOCOL = "dashboard_protocol"
PACK_DASHBOARD_VIZ = "dashboard_viz"
PACK_TASK_BODY = "task_body"

COMPLETION_CONVERSATIONAL = "conversational"
COMPLETION_ARTIFACT_SCHEMA = "artifact_schema"
COMPLETION_PIPELINE_ADVANCE = "pipeline_advance"
COMPLETION_DELIVERY = "delivery"

_CONTRACT_PROFILES = frozenset(
    {
        PROFILE_TASK_CONTRACT,
        PROFILE_PIPELINE_STEP,
        PROFILE_JOB_TASK,
    }
)


@dataclass(frozen=True)
class RunContext:
    channel: str
    trigger: str
    profile: str
    task: ActiveTask | None = None
    pipeline: PipelineState | None = None
    job_id: str | None = None
    skill: str | None = None
    prompt_packs: tuple[str, ...] = ()
    allowed_tools: frozenset[str] | None = None
    tool_budget: dict[str, int] = field(default_factory=dict)
    completion: str = COMPLETION_CONVERSATIONAL

    @property
    def is_contract_profile(self) -> bool:
        return self.profile in _CONTRACT_PROFILES

    def has_prompt_pack(self, pack: str) -> bool:
        return pack in self.prompt_packs

    @classmethod
    def resolve(
        cls,
        request: ChatRequest | Mapping[str, Any],
        *,
        task_manager: Any | None = None,
    ) -> "RunContext":
        """Resolve execution profile from a ChatRequest or raw metadata mapping."""
        if isinstance(request, ChatRequest):
            channel = str(request.channel or "")
            metadata = request.metadata if isinstance(request.metadata, dict) else {}
        else:
            channel = str(request.get("channel") or "")
            metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
            if not metadata and "active_task" in request:
                metadata = dict(request)

        active = ActiveTask.from_metadata(metadata.get("active_task"))
        pipeline = PipelineState.from_metadata(metadata.get("pipeline"))
        job_id = str(metadata.get("job_id") or "").strip() or None
        skill = str(metadata.get("invoked_skill") or "").strip() or None
        plan = bool(metadata.get("plan"))

        if active is not None and pipeline is not None:
            profile = PROFILE_PIPELINE_STEP
            trigger = TRIGGER_PIPELINE
            completion = COMPLETION_PIPELINE_ADVANCE
        elif active is not None and job_id:
            profile = PROFILE_JOB_TASK
            trigger = TRIGGER_CRON
            completion = COMPLETION_ARTIFACT_SCHEMA
        elif active is not None:
            profile = PROFILE_TASK_CONTRACT
            trigger = TRIGGER_TASK_COMMAND if metadata.get("task_command") or metadata.get("task_mode") else TRIGGER_USER_CHAT
            completion = COMPLETION_ARTIFACT_SCHEMA
        elif plan:
            profile = PROFILE_PLAN
            trigger = TRIGGER_PLAN
            completion = COMPLETION_CONVERSATIONAL
        elif job_id:
            profile = PROFILE_JOB_FREEFORM
            trigger = TRIGGER_CRON
            completion = COMPLETION_DELIVERY
        elif skill:
            profile = PROFILE_SKILL_GUIDED
            trigger = TRIGGER_SKILL
            completion = COMPLETION_CONVERSATIONAL
        else:
            profile = PROFILE_FREEFORM
            trigger = TRIGGER_USER_CHAT
            completion = COMPLETION_CONVERSATIONAL

        prompt_packs = _prompt_packs_for(profile=profile, channel=channel)
        allowed_tools = _resolve_allowed_tools(active, task_manager=task_manager)
        tool_budget = _resolve_tool_budget(active)

        return cls(
            channel=channel,
            trigger=trigger,
            profile=profile,
            task=active,
            pipeline=pipeline,
            job_id=job_id,
            skill=skill,
            prompt_packs=prompt_packs,
            allowed_tools=allowed_tools,
            tool_budget=tool_budget,
            completion=completion,
        )


def _prompt_packs_for(*, profile: str, channel: str) -> tuple[str, ...]:
    if profile in _CONTRACT_PROFILES:
        return (PACK_TASK_BODY,)
    if profile == PROFILE_JOB_FREEFORM:
        # Scheduled freeform jobs must not inherit Dashboard basket/constituent playbooks.
        return ()
    if profile == PROFILE_PLAN:
        return ()
    # freeform + skill_guided: Dashboard protocol only on the dashboard channel.
    if channel == "dashboard":
        return (PACK_DASHBOARD_PROTOCOL, PACK_DASHBOARD_VIZ)
    return ()


def _resolve_tool_budget(active: ActiveTask | None) -> dict[str, int]:
    if active is None:
        return {}
    raw = active.constraints.get("tool_budget")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            out[name] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def _resolve_allowed_tools(
    active: ActiveTask | None,
    *,
    task_manager: Any | None = None,
) -> frozenset[str] | None:
    """Return allowlist for contract profiles, or None when unrestricted."""
    if active is None:
        return None

    from_constraints = _tools_from_sequence(active.constraints.get("allowed_tools"))
    if from_constraints is not None:
        return from_constraints

    # Backward-compatible alias: some contracts may nest allowlist under constraints.
    from_required_constraint = _tools_from_sequence(active.constraints.get("required_tools"))
    if from_required_constraint is not None:
        return from_required_constraint

    if task_manager is not None:
        spec = task_manager.get_task(active.task_id)
        if spec is not None:
            from_contract = _tools_from_sequence(getattr(spec.contract, "required_tools", None))
            if from_contract is not None:
                return from_contract
    return None


def _tools_from_sequence(raw: Any) -> frozenset[str] | None:
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return None
    names = [str(item).strip() for item in raw if str(item).strip()]
    if not names:
        return None
    return frozenset(names)


def allowlist_block_message(tool_name: str, ctx: RunContext) -> str:
    allowed = sorted(ctx.allowed_tools or ())
    preview = ", ".join(allowed[:12])
    if len(allowed) > 12:
        preview = f"{preview}, ..."
    return (
        f"Tool '{tool_name}' is not in the active task allowlist "
        f"(profile={ctx.profile}). Allowed: {preview or '(none)'}. "
        "Follow the TASK.md short path; do not use basket/constituent discovery tools."
    )


__all__ = [
    "COMPLETION_ARTIFACT_SCHEMA",
    "COMPLETION_CONVERSATIONAL",
    "COMPLETION_DELIVERY",
    "COMPLETION_PIPELINE_ADVANCE",
    "PACK_DASHBOARD_PROTOCOL",
    "PACK_DASHBOARD_VIZ",
    "PACK_TASK_BODY",
    "PROFILE_FREEFORM",
    "PROFILE_JOB_FREEFORM",
    "PROFILE_JOB_TASK",
    "PROFILE_PIPELINE_STEP",
    "PROFILE_PLAN",
    "PROFILE_SKILL_GUIDED",
    "PROFILE_TASK_CONTRACT",
    "RunContext",
    "TRIGGER_CRON",
    "TRIGGER_PIPELINE",
    "TRIGGER_PLAN",
    "TRIGGER_SKILL",
    "TRIGGER_TASK_COMMAND",
    "TRIGGER_USER_CHAT",
    "allowlist_block_message",
]
