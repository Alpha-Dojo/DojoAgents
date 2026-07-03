from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from dojoagents.logging import LOGGER

EXECUTE_CODE_TOOL_NAMES = frozenset({"execute_code", "code_execution"})

ExecuteCodeBlockReason = Literal["none", "hardcoded_market_data", "presentation_only"]

_CLASSIFIER_SYSTEM_PROMPT = (
    "You review Python scripts submitted to the execute_code tool in a finance agent runtime.\n"
    "Respond ONLY with JSON (no markdown) using this schema:\n"
    "{\n"
    '  "allow_execution": boolean,\n'
    '  "block_reason": "none" | "hardcoded_market_data" | "presentation_only",\n'
    '  "explanation": string\n'
    "}\n\n"
    "Rules:\n"
    "- allow_execution=false, block_reason=hardcoded_market_data when the script embeds OHLC rows, "
    "quote values, or financial statement rows as Python literals instead of fetching live data via "
    "hermes_tools (get_ticker_price_trends, load_tool_result, etc.).\n"
    "- allow_execution=false, block_reason=presentation_only when the script mainly prints formatted "
    "text, ASCII diagrams, knowledge-graph schema docs, taxonomy tables, or design proposals without "
    "hermes_tools batch orchestration or pandas/numpy computation on fetched data.\n"
    "- allow_execution=true, block_reason=none when the script legitimately batch-calls hermes_tools, "
    "loads prior tool results, or runs numerical transforms on fetched data."
)

_BLOCK_MESSAGES = {
    "hardcoded_market_data": (
        "Blocked {tool_name}: {explanation} "
        "Do NOT inline OHLC/price rows in Python. Fetch real data inside the script via "
        "`import hermes_tools` — e.g. "
        "`hermes_tools.get_ticker_price_trends({{'ticker': '0700', 'market': 'hk'}})` or "
        "`hermes_tools.load_tool_result('<call_id>')`, then parse with `hermes_tools.tool_json(res)`."
    ),
    "presentation_only": (
        "Blocked {tool_name}: {explanation} "
        "Do NOT use execute_code for ASCII diagrams, schema design docs, or formatted text. "
        "Write those directly in the assistant reply (markdown/tables). "
        "Use execute_code only for hermes_tools batch orchestration or pandas/numpy computation "
        "on fetched tool data."
    ),
}

_GUARDRAIL_CODES = {
    "hardcoded_market_data": "execute_code_inline_market_data",
    "presentation_only": "execute_code_presentation_only",
}


@dataclass(frozen=True)
class ExecuteCodeClassification:
    allow_execution: bool = True
    block_reason: ExecuteCodeBlockReason = "none"
    explanation: str = ""


DEFAULT_EXECUTE_CODE_CLASSIFICATION = ExecuteCodeClassification()


def _parse_classifier_json(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _coerce_execute_code_classification(data: dict[str, Any]) -> ExecuteCodeClassification:
    allow_execution = bool(data.get("allow_execution", True))
    raw_reason = str(data.get("block_reason") or "none").strip().lower()
    valid_reasons = {"none", "hardcoded_market_data", "presentation_only"}
    block_reason: ExecuteCodeBlockReason = raw_reason if raw_reason in valid_reasons else "none"
    explanation = str(data.get("explanation") or "").strip()
    if allow_execution:
        return ExecuteCodeClassification(allow_execution=True, block_reason="none", explanation=explanation)
    if block_reason == "none":
        block_reason = "presentation_only"
    return ExecuteCodeClassification(
        allow_execution=False,
        block_reason=block_reason,
        explanation=explanation or block_reason.replace("_", " "),
    )


def _code_cache_key(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _clip_code_for_classifier(code: str, *, max_chars: int = 12000) -> str:
    text = code or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n# … [truncated for classifier]"


async def classify_execute_code(
    code: str,
    user_message: str,
    llm_provider: Any,
    *,
    model: str,
    request_metadata: dict[str, Any] | None = None,
) -> ExecuteCodeClassification:
    """Use the configured LLM to decide whether an execute_code script should run."""
    normalized = (code or "").strip()
    if not normalized:
        return DEFAULT_EXECUTE_CODE_CLASSIFICATION

    metadata = request_metadata if isinstance(request_metadata, dict) else {}
    cache_bucket = metadata.setdefault("_execute_code_classifications", {})
    cache_key = _code_cache_key(normalized)
    if isinstance(cache_bucket, dict) and cache_key in cache_bucket:
        cached = cache_bucket[cache_key]
        if isinstance(cached, dict):
            return _coerce_execute_code_classification(cached)

    clipped_code = _clip_code_for_classifier(normalized)
    user_payload = (
        f"Latest user message:\n{(user_message or '').strip() or '(empty)'}\n\n"
        f"Proposed execute_code script:\n```python\n{clipped_code}\n```"
    )
    messages = [
        {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]
    try:
        result = await llm_provider.chat(messages, tools=[], model=model)
        data = _parse_classifier_json(result.content)
        if data is None:
            LOGGER.warning("execute_code classifier returned non-JSON content; allowing execution")
            return DEFAULT_EXECUTE_CODE_CLASSIFICATION
        classification = _coerce_execute_code_classification(data)
        if isinstance(cache_bucket, dict):
            cache_bucket[cache_key] = {
                "allow_execution": classification.allow_execution,
                "block_reason": classification.block_reason,
                "explanation": classification.explanation,
            }
        return classification
    except Exception:
        LOGGER.exception("execute_code classification failed; allowing execution")
        return DEFAULT_EXECUTE_CODE_CLASSIFICATION


def execute_code_guardrail_from_classification(
    tool_name: str,
    classification: ExecuteCodeClassification,
) -> tuple[bool, str, str]:
    """Return (blocked, message, guardrail_code)."""
    if classification.allow_execution or classification.block_reason == "none":
        return False, "", "allow"
    guardrail_code = _GUARDRAIL_CODES.get(classification.block_reason, "execute_code_classifier_block")
    template = _BLOCK_MESSAGES.get(classification.block_reason, "Blocked {tool_name}: {explanation}")
    explanation = classification.explanation or classification.block_reason.replace("_", " ")
    message = template.format(tool_name=tool_name, explanation=explanation)
    return True, message, guardrail_code
