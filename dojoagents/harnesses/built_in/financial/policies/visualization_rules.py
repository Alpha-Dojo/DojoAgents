"""Declarative visualization policy for dashboard agent_viz_build.

New product scenarios should register rules via ``register_viz_policy_rule`` instead
of scattering one-off prompt edits. Rules return a ``VizPolicyMatch`` when they
apply; the highest ``priority`` wins.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from dojoagents.agent.models import ChatRequest, ToolResult

VizStance = Literal["encouraged", "optional", "forbidden"]

VizPolicyRule = Callable[["VizPolicyContext"], "VizPolicyMatch | None"]

_PORTFOLIO_WRITE_TOOLS = frozenset(
    {
        "portfolio_write_create",
        "portfolio_write_rename",
        "portfolio_write_delete",
        "portfolio_write_add_candidate",
        "portfolio_write_add_candidates",
        "portfolio_write_add_holding",
        "portfolio_write_add_holdings",
        "portfolio_write_create_order",
        "portfolio_write_create_orders",
        "portfolio_write_sync_positions",
        "portfolio_write_remove_holding",
        "portfolio_write_remove_candidates",
        "portfolio_write_auto_allocate",
    }
)

_DATA_READ_TOOLS = frozenset(
    {
        "portfolio_read_detail",
        "portfolio_read_list",
        "portfolio_read_search",
        "get_ticker_price_trends",
        "get_ticker_financials",
        "get_ticker_realtime_quote",
        "get_market_overview",
        "get_sector_movers",
        "get_sector_analysis",
        "screen_market_stocks",
        "filter_sector_constituents",
        "search_company_ticker",
        "search_sector_taxonomy",
        "get_taxonomy_tree",
    }
)

_COMPUTE_TOOLS = frozenset({"execute_code", "code_execution"})


@dataclass(frozen=True)
class VizPolicyMatch:
    scene_id: str
    stance: VizStance
    reason_en: str
    reason_zh: str
    priority: int = 0


@dataclass(frozen=True)
class VizPolicyContext:
    channel: str
    user_message: str
    locale: str
    tool_results: tuple[ToolResult, ...] = ()
    tool_trace: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class VizPolicyDecision:
    match: VizPolicyMatch
    block_agent_viz_build: bool
    block_message: str = ""


_BUILTIN_SCENES: tuple[tuple[str, VizStance, str, str], ...] = (
    (
        "portfolio_mutating_task",
        "forbidden",
        "Portfolio write/delete/order flows are confirmation tasks. Summarize in markdown; "
        "reuse auto viz_blocks from portfolio_read_detail if present. Do NOT call agent_viz_build.",
        "组合写入/删改/下单/清仓属于交易确认类任务。用正文 markdown 汇报即可；" "可复用 portfolio_read_detail 自动附带的 viz_blocks，禁止再调 agent_viz_build。",
    ),
    (
        "portfolio_eval_accepted",
        "forbidden",
        "portfolio_eval_submit already accepted — task is closed. Reply to the user and stop; " "no extra visualization.",
        "portfolio_eval_submit 已通过，任务已闭环。直接回复用户，不要追加可视化。",
    ),
    (
        "quant_viz_data_ready",
        "encouraged",
        "Structured VIZ_DATA / viz_hint is available from execute_code. " "Call agent_viz_build with mapping_hint when a chart adds insight beyond stdout.",
        "execute_code 已产出 VIZ_DATA / viz_hint。需要图表时调用 agent_viz_build（带 mapping_hint）。",
    ),
    (
        "exploratory_read_analysis",
        "optional",
        "Read-only analysis: prefer viz_blocks auto-attached to data tools. " "Call agent_viz_build only when you need a chart type the auto blocks do not provide.",
        "只读分析：优先使用数据工具自动附带的 viz_blocks；" "仅当需要 auto 未提供的图表类型时才调用 agent_viz_build。",
    ),
    (
        "default_dashboard",
        "optional",
        "Default: markdown for narrative; agent_viz_build only when it clearly adds a chart " "the user asked for or auto viz_blocks cannot express.",
        "默认：正文负责叙述；仅在用户明确要图或 auto viz_blocks 无法表达时才用 agent_viz_build。",
    ),
)

_extra_rules: list[tuple[int, VizPolicyRule]] = []


def register_viz_policy_rule(rule: VizPolicyRule, *, priority: int = 10) -> None:
    """Register an extension rule. Higher priority overrides lower on conflict."""
    _extra_rules.append((priority, rule))
    _extra_rules.sort(key=lambda item: item[0], reverse=True)


def _localized(match: VizPolicyMatch, locale: str) -> str:
    return match.reason_zh if locale == "zh" else match.reason_en


def _eval_accepted(results: tuple[ToolResult, ...]) -> bool:
    for result in results:
        if not result.ok or result.name != "portfolio_eval_submit":
            continue
        data = result.data
        if isinstance(data, dict) and data.get("accepted"):
            return True
    return False


def _any_ok_tool(results: tuple[ToolResult, ...], names: frozenset[str]) -> bool:
    return any(result.ok and result.name in names for result in results)


def _last_ok_tool(results: tuple[ToolResult, ...], name: str) -> ToolResult | None:
    for result in reversed(results):
        if result.ok and result.name == name:
            return result
    return None


def _has_viz_hint_payload(result: ToolResult) -> bool:
    content = str(result.content or "")
    if "--- viz_hint ---" in content:
        return True
    data = result.data
    if isinstance(data, dict) and ((isinstance(data.get("dates"), list) and isinstance(data.get("prices"), list)) or data.get("drawdown_pcts") is not None):
        return True
    return False


def _rule_portfolio_eval_accepted(ctx: VizPolicyContext) -> VizPolicyMatch | None:
    if not _eval_accepted(ctx.tool_results):
        return None
    _scene_id, stance, reason_en, reason_zh = _BUILTIN_SCENES[1]
    return VizPolicyMatch(
        scene_id=_scene_id,
        stance=stance,
        reason_en=reason_en,
        reason_zh=reason_zh,
        priority=100,
    )


def _rule_portfolio_mutating_task(ctx: VizPolicyContext) -> VizPolicyMatch | None:
    if not _any_ok_tool(ctx.tool_results, _PORTFOLIO_WRITE_TOOLS):
        return None
    _scene_id, stance, reason_en, reason_zh = _BUILTIN_SCENES[0]
    return VizPolicyMatch(
        scene_id=_scene_id,
        stance=stance,
        reason_en=reason_en,
        reason_zh=reason_zh,
        priority=95,
    )


def _rule_quant_viz_data_ready(ctx: VizPolicyContext) -> VizPolicyMatch | None:
    for result in reversed(ctx.tool_results):
        if not result.ok or result.name not in _COMPUTE_TOOLS:
            continue
        if _has_viz_hint_payload(result):
            _scene_id, stance, reason_en, reason_zh = _BUILTIN_SCENES[2]
            return VizPolicyMatch(
                scene_id=_scene_id,
                stance=stance,
                reason_en=reason_en,
                reason_zh=reason_zh,
                priority=60,
            )
        break
    return None


def _rule_exploratory_read_analysis(ctx: VizPolicyContext) -> VizPolicyMatch | None:
    if _any_ok_tool(ctx.tool_results, _PORTFOLIO_WRITE_TOOLS):
        return None
    if not _any_ok_tool(ctx.tool_results, _DATA_READ_TOOLS):
        return None
    _scene_id, stance, reason_en, reason_zh = _BUILTIN_SCENES[3]
    return VizPolicyMatch(
        scene_id=_scene_id,
        stance=stance,
        reason_en=reason_en,
        reason_zh=reason_zh,
        priority=30,
    )


def _rule_default(ctx: VizPolicyContext) -> VizPolicyMatch:
    _scene_id, stance, reason_en, reason_zh = _BUILTIN_SCENES[4]
    return VizPolicyMatch(
        scene_id=_scene_id,
        stance=stance,
        reason_en=reason_en,
        reason_zh=reason_zh,
        priority=0,
    )


_BUILTIN_RULES: tuple[tuple[int, VizPolicyRule], ...] = (
    (100, _rule_portfolio_eval_accepted),
    (95, _rule_portfolio_mutating_task),
    (60, _rule_quant_viz_data_ready),
    (30, _rule_exploratory_read_analysis),
)


def _all_rules() -> list[tuple[int, VizPolicyRule]]:
    merged = list(_BUILTIN_RULES) + list(_extra_rules)
    merged.sort(key=lambda item: item[0], reverse=True)
    return merged


def resolve_viz_policy(ctx: VizPolicyContext) -> VizPolicyMatch:
    best: VizPolicyMatch | None = None
    for _priority, rule in _all_rules():
        match = rule(ctx)
        if match is None:
            continue
        if best is None or match.priority > best.priority:
            best = match
    return best or _rule_default(ctx)


def evaluate_viz_policy(ctx: VizPolicyContext) -> VizPolicyDecision:
    match = resolve_viz_policy(ctx)
    if match.stance == "forbidden":
        return VizPolicyDecision(
            match=match,
            block_agent_viz_build=True,
            block_message=_localized(match, ctx.locale),
        )
    return VizPolicyDecision(match=match, block_agent_viz_build=False)


def check_agent_viz_build(ctx: VizPolicyContext) -> VizPolicyDecision:
    return evaluate_viz_policy(ctx)


def build_viz_policy_context(
    request: ChatRequest,
    *,
    tool_results: list[ToolResult] | None = None,
    tool_trace: list[dict[str, Any]] | None = None,
) -> VizPolicyContext:
    locale = str(request.metadata.get("locale") or "en")
    return VizPolicyContext(
        channel=str(request.channel or ""),
        user_message=str(request.message or ""),
        locale=locale,
        tool_results=tuple(tool_results or ()),
        tool_trace=tuple(tool_trace or ()),
    )


def build_viz_policy_catalog(locale: str) -> str:
    """Static scene matrix injected into the dashboard system prompt."""
    if locale == "zh":
        header = "## 可视化策略（agent_viz_build）\n\n"
        intro = (
            "可视化分两层：**数据工具自动附带的 viz_blocks**（无需再调工具）与 "
            "**显式 agent_viz_build**（仅在下表允许时）。新场景请通过 "
            "`dojoagents.harnesses.built_in.financial.policies.visualization_rules.register_viz_policy_rule` 注册规则，勿改 prompt 散点补丁。\n\n"
        )
        stance_labels = {"encouraged": "鼓励", "optional": "可选", "forbidden": "禁止"}
        columns = "| 场景 ID | 策略 | 说明 |\n|--------|------|------|\n"
    else:
        header = "## Visualization policy (agent_viz_build)\n\n"
        intro = (
            "Two layers: **auto viz_blocks** on data-tool results (no extra call) vs "
            "**explicit agent_viz_build** (only when the table allows). "
            "Register new scenes via `dojoagents.harnesses.built_in.financial.policies.visualization_rules.register_viz_policy_rule` "
            "instead of ad-hoc prompt edits.\n\n"
        )
        stance_labels = {"encouraged": "encouraged", "optional": "optional", "forbidden": "forbidden"}
        columns = "| Scene ID | Stance | Guidance |\n|----------|--------|----------|\n"

    rows: list[str] = []
    for scene_id, stance, reason_en, reason_zh in _BUILTIN_SCENES:
        reason = reason_zh if locale == "zh" else reason_en
        rows.append(f"| `{scene_id}` | {stance_labels[stance]} | {reason} |")
    return header + intro + columns + "\n".join(rows)


def build_viz_policy_turn_anchor(request: ChatRequest, locale: str) -> str:
    """Lightweight pre-tool hint from the user message (before tool trace exists)."""
    message = str(request.message or "").strip()
    if not message:
        return ""

    ctx = build_viz_policy_context(request)
    match = resolve_viz_policy(ctx)

    transactional_markers = (
        "清仓",
        "全部卖出",
        "卖出",
        "减仓",
        "买入",
        "建仓",
        "创建组合",
        "添加候选",
        "liquidate",
        "sell all",
        "create order",
    )
    if any(marker.lower() in message.lower() for marker in transactional_markers):
        if locale == "zh":
            return "## 本轮可视化策略\n" "检测到组合交易/写入类请求：任务完成后用 markdown 确认即可，" "**禁止** 调用 agent_viz_build。"
        return "## Visualization this turn\n" "Portfolio write/trade task detected: confirm in markdown when done; " "do NOT call agent_viz_build."

    if match.stance == "encouraged":
        if locale == "zh":
            return f"## 本轮可视化策略\n{_localized(match, locale)}"
        return f"## Visualization this turn\n{_localized(match, locale)}"
    return ""
