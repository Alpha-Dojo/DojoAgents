from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

IDEMPOTENT_TOOL_NAMES = frozenset(
    {
        "read_file",
        "search_files",
        "web_search",
        "list_dir",
        "skills_list",
        "skill_view",
    }
)

MUTATING_TOOL_NAMES = frozenset(
    {
        "terminal",
        "execute_code",
        "write_file",
        "patch",
        "skill_manage",
    }
)


@dataclass(frozen=True)
class ToolCallSignature:
    tool_name: str
    args_hash: str

    @classmethod
    def from_call(cls, tool_name: str, args: Mapping[str, Any] | None) -> ToolCallSignature:
        canonical = json.dumps(
            args or {},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        args_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(tool_name=tool_name, args_hash=args_hash)


@dataclass(frozen=True)
class ToolGuardrailDecision:
    action: str = "allow"  # allow | warn | block | halt
    code: str = "allow"
    message: str = ""
    tool_name: str = ""
    count: int = 0
    signature: ToolCallSignature | None = None

    @property
    def allows_execution(self) -> bool:
        return self.action in {"allow", "warn"}

    @property
    def should_halt(self) -> bool:
        return self.action in {"block", "halt"}


class ToolCallGuardrailController:
    def __init__(
        self,
        exact_failure_warn_after: int = 2,
        exact_failure_block_after: int = 5,
        same_tool_failure_warn_after: int = 3,
        same_tool_failure_halt_after: int = 8,
        no_progress_warn_after: int = 2,
        no_progress_block_after: int = 5,
    ):
        self.exact_failure_warn_after = exact_failure_warn_after
        self.exact_failure_block_after = exact_failure_block_after
        self.same_tool_failure_warn_after = same_tool_failure_warn_after
        self.same_tool_failure_halt_after = same_tool_failure_halt_after
        self.no_progress_warn_after = no_progress_warn_after
        self.no_progress_block_after = no_progress_block_after

        self._exact_failure_counts: dict[ToolCallSignature, int] = {}
        self._same_tool_failure_counts: dict[str, int] = {}
        self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}
        self._halt_decision: ToolGuardrailDecision | None = None

    def reset_for_turn(self) -> None:
        self._exact_failure_counts.clear()
        self._same_tool_failure_counts.clear()
        self._no_progress.clear()
        self._halt_decision = None

    def before_call(self, tool_name: str, args: Mapping[str, Any] | None) -> ToolGuardrailDecision:
        signature = ToolCallSignature.from_call(tool_name, args)

        if tool_name == "terminal":
            command = str((args or {}).get("command") or "").lower()
            if "dojo_tools" in command or "load_tool_result" in command:
                decision = ToolGuardrailDecision(
                    action="block",
                    code="terminal_dojo_tools_blocked",
                    message=(
                        "Blocked terminal: dojo_tools.load_tool_result only works inside execute_code. "
                        "Read positions[] from the portfolio_read_detail artifact pointer, or use "
                        "execute_code with dojo_tools.load_tool_result(call_id)."
                    ),
                    tool_name=tool_name,
                    signature=signature,
                )
                self._halt_decision = decision
                return decision

        exact_count = self._exact_failure_counts.get(signature, 0)
        if exact_count >= self.exact_failure_block_after:
            decision = ToolGuardrailDecision(
                action="block",
                code="repeated_exact_failure_block",
                message=(
                    f"Blocked {tool_name}: the same tool call failed {exact_count} "
                    "times with identical arguments. Stop retrying it unchanged; "
                    "change strategy or explain the blocker."
                ),
                tool_name=tool_name,
                count=exact_count,
                signature=signature,
            )
            self._halt_decision = decision
            return decision

        if tool_name in IDEMPOTENT_TOOL_NAMES:
            record = self._no_progress.get(signature)
            if record is not None:
                _result_hash, repeat_count = record
                if repeat_count >= self.no_progress_block_after:
                    decision = ToolGuardrailDecision(
                        action="block",
                        code="idempotent_no_progress_block",
                        message=(
                            f"Blocked {tool_name}: this read-only call returned the same "
                            f"result {repeat_count} times. Stop repeating it unchanged; "
                            "use the result already provided or try a different query."
                        ),
                        tool_name=tool_name,
                        count=repeat_count,
                        signature=signature,
                    )
                    self._halt_decision = decision
                    return decision

        return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: str | None,
        failed: bool,
    ) -> ToolGuardrailDecision:
        signature = ToolCallSignature.from_call(tool_name, args)

        if failed:
            exact_count = self._exact_failure_counts.get(signature, 0) + 1
            self._exact_failure_counts[signature] = exact_count
            self._no_progress.pop(signature, None)

            same_count = self._same_tool_failure_counts.get(tool_name, 0) + 1
            self._same_tool_failure_counts[tool_name] = same_count

            if same_count >= self.same_tool_failure_halt_after:
                decision = ToolGuardrailDecision(
                    action="halt",
                    code="same_tool_failure_halt",
                    message=(
                        f"Stopped {tool_name}: it failed {same_count} times this turn. "
                        "Stop retrying the same failing tool path and choose a different approach."
                    ),
                    tool_name=tool_name,
                    count=same_count,
                    signature=signature,
                )
                self._halt_decision = decision
                return decision

            if exact_count >= self.exact_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="repeated_exact_failure_warning",
                    message=(
                        f"{tool_name} has failed {exact_count} times with identical arguments. "
                        "This looks like a loop; inspect the error and change strategy "
                        "instead of retrying it unchanged."
                    ),
                    tool_name=tool_name,
                    count=exact_count,
                    signature=signature,
                )

            if same_count >= self.same_tool_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="same_tool_failure_warning",
                    message=(
                        f"{tool_name} has failed {same_count} times this turn. "
                        "This looks like a loop. Do not switch to text-only replies; keep using tools, "
                        "but diagnose the failure before retrying."
                    ),
                    tool_name=tool_name,
                    count=same_count,
                    signature=signature,
                )

            return ToolGuardrailDecision(tool_name=tool_name, count=exact_count, signature=signature)

        self._exact_failure_counts.pop(signature, None)
        self._same_tool_failure_counts.pop(tool_name, None)

        if tool_name not in IDEMPOTENT_TOOL_NAMES:
            self._no_progress.pop(signature, None)
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

        # Compute result hash
        result_hash = hashlib.sha256((result or "").encode("utf-8")).hexdigest()
        previous = self._no_progress.get(signature)
        repeat_count = 1
        if previous is not None and previous[0] == result_hash:
            repeat_count = previous[1] + 1
        self._no_progress[signature] = (result_hash, repeat_count)

        if repeat_count >= self.no_progress_warn_after:
            return ToolGuardrailDecision(
                action="warn",
                code="idempotent_no_progress_warning",
                message=(
                    f"{tool_name} returned the same result {repeat_count} times. "
                    "Use the result already provided or change the query instead of "
                    "repeating it unchanged."
                ),
                tool_name=tool_name,
                count=repeat_count,
                signature=signature,
            )

        return ToolGuardrailDecision(tool_name=tool_name, count=repeat_count, signature=signature)


def toolguard_synthetic_result(decision: ToolGuardrailDecision) -> dict[str, Any]:
    return {
        "content": json.dumps(
            {
                "error": decision.message,
                "guardrail": {
                    "action": decision.action,
                    "code": decision.code,
                    "message": decision.message,
                    "tool_name": decision.tool_name,
                    "count": decision.count,
                },
            },
            ensure_ascii=False,
        ),
        "metadata": {"ok": False, "stopped": decision.action},
    }


def append_toolguard_guidance(result_content: str, decision: ToolGuardrailDecision) -> str:
    if decision.action not in {"warn", "halt"} or not decision.message:
        return result_content
    label = "Tool loop hard stop" if decision.action == "halt" else "Tool loop warning"
    suffix = (
        f"\n\n[{label}: "
        f"{decision.code}; count={decision.count}; {decision.message}]"
    )
    return (result_content or "") + suffix
