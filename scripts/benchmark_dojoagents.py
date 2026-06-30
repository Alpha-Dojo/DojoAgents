#!/usr/bin/env python3
"""
Programmatic benchmark: send each question from the DojoBenchmark CSVs to the
DojoAgents dashboard chat endpoint and optionally score responses with an LLM judge.

Target:
  Backend: http://localhost:8000  (FastAPI dashboard server)

Agent entry point:
  POST /api/chat   — OpenAI-compatible, supports both streaming and non-streaming

Request format (OpenAI-compatible):
  {"messages": [{"role": "user", "content": "..."}], "model": "default", "stream": false}

Response format (non-streaming):
  {"choices": [{"message": {"role": "assistant", "content": "..."}}], "content": "...", ...}

Response format (streaming SSE):
  data: {"choices": [{"delta": {"content": "..."}}], ...}
  data: [DONE]

Usage:
  # non-streaming, default model, all sheets
  python scripts/benchmark_dojoagents.py

  # force a model name, streaming mode, limit to 3 questions per sheet
  python scripts/benchmark_dojoagents.py --model my-model --stream --limit 3

  # dry-run: print questions without calling the API
  python scripts/benchmark_dojoagents.py --dry-run

  # save JSON results to a specific path
  python scripts/benchmark_dojoagents.py --out results.json

  # skip LLM judge scoring
  python scripts/benchmark_dojoagents.py --no-judge

  # run only sheet 1
  python scripts/benchmark_dojoagents.py --sheet 1
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("httpx is required: pip install httpx", file=sys.stderr)
    sys.exit(1)

# ── config ────────────────────────────────────────────────────────────────────

API_BASE = "http://localhost:8000"
CHAT_ENDPOINT = f"{API_BASE}/api/chat"

# CSVs live inside the project under data/benchmark/
_BENCHMARK_DIR = Path(__file__).parent.parent / "data" / "benchmark"
SHEET1_CSV = _BENCHMARK_DIR / "DojoBenchmark_sheet1.csv"
SHEET2_CSV = _BENCHMARK_DIR / "DojoBenchmark_sheet2.csv"
SHEET3_CSV = _BENCHMARK_DIR / "DojoBenchmark_sheet3_extended.csv"

# Default output root: data/benchmark_results/
_RESULTS_DIR = Path(__file__).parent.parent / "data" / "benchmark_results"

# LLM judge — reads from dedicated JUDGE_* env vars to decouple from the agent model.
# JUDGE_OPENAI_MODEL defaults to claude-haiku-4-5-20251001 (different from the evaluated agent)
# to avoid circular self-scoring.  Override with JUDGE_OPENAI_MODEL or --judge-model.
_JUDGE_MODEL = os.getenv("JUDGE_OPENAI_MODEL") or os.getenv("OPENAI_MODEL", "claude-haiku-4-5-20251001")
_JUDGE_API_KEY = os.getenv("JUDGE_API_KEY") or os.getenv("OPENAI_API_KEY", "")
_JUDGE_BASE_URL = (os.getenv("JUDGE_BASE_URL") or os.getenv("OPENAI_BASE_URL", "")).strip() or None

# Sheet 3 subcategories whose reference trajectories use API fields / params
# absent from the real backend — LLM judge is suppressed for these.
_SHEET3_JUDGE_SKIP: dict[str, str] = {
    "多季度 Beat/Miss 连续追踪": (
        "trajectory uses get_ticker_financials(periods=, guidance_mid, beat_miss_pct) "
        "— params/fields absent from real API"
    ),
    "毛利率 Guidance 与实际值对标": (
        "trajectory uses get_ticker_financials(metrics=, guidance_low, guidance_high) "
        "— params/fields absent from real API"
    ),
    "持仓集中度与风险雷达诊断": (
        "trajectory uses get_portfolio_analysis(include_risk_exposure=True) and risk_exposure "
        "response field — neither exists in PortfolioAnalysisResponse"
    ),
    "Brinson 归因分解与超额收益来源识别": (
        "trajectory uses get_portfolio_analysis(include_attribution=True) and attribution "
        "response field — neither exists in PortfolioAnalysisResponse"
    ),
    "条件触发式再平衡决策": (
        "trajectory uses filter_sector_constituents(sort_by=, min_div_yield=) — params absent "
        "from real API"
    ),
    "GAAP 与 Non-GAAP 财务调整项解读": (
        "trajectory uses get_ticker_financials(include_gaap_bridge=True) — param absent from "
        "real API; TickerFinancialsResponse has no GAAP bridge reconciliation field"
    ),
}

_JUDGE_SYSTEM = """\
You are an objective evaluator assessing an AI financial assistant's response quality.
Score the response on a 1-5 scale across three dimensions:

1. **Relevance** — Does the reply address the user's intent?
2. **Completeness** — Are all key points from the reference trajectory covered?
3. **Accuracy** — Are facts, numbers, and reasoning correct (relative to reference)?

Return ONLY valid JSON with this schema (no markdown fences):
{
  "relevance": <1-5>,
  "completeness": <1-5>,
  "accuracy": <1-5>,
  "overall": <1-5>,
  "rationale": "<one sentence>"
}
"""

# Used for live-data questions where reference values may be stale.
# Accuracy is replaced by "Tool Appropriateness" so stale numbers don't tank the score.
_JUDGE_SYSTEM_LIVE_DATA = """\
You are an objective evaluator assessing an AI financial assistant's response quality.
The reference trajectory below was written at a different point in time, so the specific
numeric values in the reference may be stale. Do NOT penalize the agent for returning
different numbers than the reference.

Score the response on a 1-5 scale across three dimensions:

1. **Relevance** — Does the reply address the user's intent?
2. **Completeness** — Are all key structural steps from the reference trajectory present?
3. **Tool Appropriateness** — Did the agent call the right tools in a sensible order?
   (Use this instead of factual accuracy since reference data may be outdated.)

Return ONLY valid JSON with this schema (no markdown fences):
{
  "relevance": <1-5>,
  "completeness": <1-5>,
  "accuracy": <1-5>,
  "overall": <1-5>,
  "rationale": "<one sentence>"
}
Note: populate "accuracy" with your Tool Appropriateness score.
"""

# Used when the agent under test has no market-data tools available (e.g. dashboard context).
# Scoring shifts from tool-call compliance to reasoning quality and honest disclosure.
_JUDGE_SYSTEM_NO_TOOLS = """\
You are an objective evaluator assessing an AI financial assistant that does NOT have
access to real-time market data tools. The reference trajectory may show tool calls that
this agent cannot make — do NOT penalize for missing tool usage.

Score the response on a 1-5 scale across three dimensions:

1. **Relevance** — Does the reply address the user's intent and show domain understanding?
2. **Completeness** — Does it cover the key concepts from the reference, even without live data?
3. **Reasoning Quality** — Is the analytical reasoning sound, honest about data limitations,
   and useful to the user despite lacking live data? (Use this instead of factual accuracy.)

Return ONLY valid JSON with this schema (no markdown fences):
{
  "relevance": <1-5>,
  "completeness": <1-5>,
  "accuracy": <1-5>,
  "overall": <1-5>,
  "rationale": "<one sentence>"
}
Note: populate "accuracy" with your Reasoning Quality score.
"""

_JUDGE_USER_TEMPLATE = """\
## Reference trajectory (ground truth — what an ideal agent would do)
{desired_output}

## Actual agent reply
{actual_reply}

## User question
{question}

Evaluate and return JSON scores.
"""


# ── data loading ──────────────────────────────────────────────────────────────

@dataclass
class BenchmarkQuestion:
    sheet: str
    category: str
    subcategory: str
    difficulty: str
    question: str
    desired_output: str = ""
    display_style: str = ""


def _extract_q1(examples_cell: str) -> str:
    """Pull the first quoted question out of a multi-Q examples cell."""
    for line in examples_cell.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(("Q1:", "Q1：")):
            text = line.split(":", 1)[1].strip()
        else:
            text = line
        text = text.strip('"').strip('“').strip('”').strip()
        if text:
            return text
    return examples_cell[:200]


def load_sheet1(csv_path: Path, limit: int | None = None) -> list[BenchmarkQuestion]:
    """Load DojoBenchmark sheet (columns: 大类, 小类, 难度, 定义, 案例, 展示样式, 轨迹)."""
    questions: list[BenchmarkQuestion] = []
    current_category = ""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("问题大类"):
                continue
            category = row[0].strip() if row[0].strip() else current_category
            if row[0].strip():
                current_category = category
            subcategory = row[1].strip() if len(row) > 1 else ""
            difficulty = row[2].strip() if len(row) > 2 else ""
            examples = row[4].strip() if len(row) > 4 else ""
            display = row[5].strip() if len(row) > 5 else ""
            desired_output = row[6].strip() if len(row) > 6 else ""
            if not examples:
                continue
            q = _extract_q1(examples)
            if q:
                questions.append(BenchmarkQuestion(
                    sheet="DojoBenchmark",
                    category=category,
                    subcategory=subcategory,
                    difficulty=difficulty,
                    question=q,
                    desired_output=desired_output,
                    display_style=display,
                ))
            if limit and len(questions) >= limit:
                break
    return questions


def load_sheet2(csv_path: Path, limit: int | None = None) -> list[BenchmarkQuestion]:
    """Load Claude-Benchmark sheet (columns: 类别, 难度, 定义, 样例)."""
    questions: list[BenchmarkQuestion] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            if "Task Name" in row[0] or "Claude&OpenAI" in row[0]:
                continue
            category = row[0].strip()
            difficulty = row[1].strip() if len(row) > 1 else ""
            example = row[3].strip() if len(row) > 3 else ""
            if not example or not category:
                continue
            q = example.strip('"').strip('“').strip('”').strip()
            questions.append(BenchmarkQuestion(
                sheet="Claude-Benchmark",
                category=category,
                subcategory="",
                difficulty=difficulty,
                question=q,
                desired_output="",
            ))
            if limit and len(questions) >= limit:
                break
    return questions


def load_sheet3(csv_path: Path, limit: int | None = None) -> list[BenchmarkQuestion]:
    """Load extended benchmark sheet (same column layout as sheet 1)."""
    questions: list[BenchmarkQuestion] = []
    current_category = ""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("问题大类"):
                continue
            category = row[0].strip() if row[0].strip() else current_category
            if row[0].strip():
                current_category = category
            subcategory = row[1].strip() if len(row) > 1 else ""
            difficulty = row[2].strip() if len(row) > 2 else ""
            examples = row[4].strip() if len(row) > 4 else ""
            display = row[5].strip() if len(row) > 5 else ""
            desired_output = row[6].strip() if len(row) > 6 else ""
            if not examples:
                continue
            q = _extract_q1(examples)
            if q:
                questions.append(BenchmarkQuestion(
                    sheet="Extended-Benchmark",
                    category=category,
                    subcategory=subcategory,
                    difficulty=difficulty,
                    question=q,
                    desired_output=desired_output,
                    display_style=display,
                ))
            if limit and len(questions) >= limit:
                break
    return questions


# ── API helpers ───────────────────────────────────────────────────────────────

def build_payload(
    messages: list[dict[str, str]],
    model: str,
    *,
    stream: bool = False,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "stream": stream,
        "metadata": {"locale": "zh", "event_format": "dojo.v2"},
    }


def ask_chat(
    client: httpx.Client,
    messages: list[dict[str, str]],
    model: str,
) -> tuple[str, list[Any], float]:
    """Non-streaming POST /api/chat — returns (reply_text, tool_calls, latency_ms)."""
    payload = build_payload(messages, model, stream=False)
    t0 = time.perf_counter()
    resp = client.post(CHAT_ENDPOINT, json=payload, timeout=3600)
    latency_ms = (time.perf_counter() - t0) * 1000
    resp.raise_for_status()
    data = resp.json()
    # Primary: OpenAI choices format; fallback: legacy "content" field
    choices = data.get("choices") or []
    if choices:
        reply = (choices[0].get("message") or {}).get("content") or ""
    else:
        reply = data.get("content", "")
    # Tool calls surface in dojo extension events if present
    tool_calls = _extract_tool_calls_from_dojo(data)
    return reply, tool_calls, latency_ms


def _extract_tool_calls_from_dojo(data: dict[str, Any]) -> list[Any]:
    """Extract tool call records from the dojo extension block if present."""
    dojo = data.get("dojo")
    if not isinstance(dojo, dict):
        return []
    events = dojo.get("events") or []
    return [e for e in events if isinstance(e, dict) and e.get("type") == "tool_start"]


def ask_stream(
    client: httpx.Client,
    messages: list[dict[str, str]],
    model: str,
) -> tuple[str, list[Any], float]:
    """Streaming SSE POST /api/chat — collects deltas, returns (text, tool_calls, latency_ms)."""
    payload = build_payload(messages, model, stream=True)
    t0 = time.perf_counter()
    parts: list[str] = []
    tool_calls: list[Any] = []
    with client.stream("POST", CHAT_ENDPOINT, json=payload, timeout=3600) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw.strip() == "[DONE]":
                break
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            for choice in choices:
                delta = choice.get("delta") or {}
                # text delta
                content = delta.get("content")
                if content:
                    parts.append(content)
                # tool call delta (name only — arguments may stream in pieces)
                for tc in delta.get("tool_calls") or []:
                    fn = (tc.get("function") or {})
                    if fn.get("name"):
                        tool_calls.append({"type": "tool_start", "tool": fn["name"]})
            # dojo_event carries richer typed events
            dojo_event = event.get("dojo_event") or {}
            if dojo_event.get("type") == "tool_start":
                tool_calls.append(dojo_event)
    latency_ms = (time.perf_counter() - t0) * 1000
    return "".join(parts), tool_calls, latency_ms


_CONTINUATION_PROMPT = "请继续完成上述任务，直到给出完整的最终答案。"


def ask_until_complete(
    client: httpx.Client,
    initial_messages: list[dict[str, str]],
    model: str,
    *,
    use_stream: bool = False,
    max_continuation: int = 5,
    verbose: bool = False,
) -> tuple[str, list[Any], float, list[ConversationTurn]]:
    """Drive the agent until it produces a non-empty reply, nudging if needed.

    Returns (final_reply, accumulated_tool_calls, total_latency_ms, turns).
    """
    messages: list[dict[str, str]] = list(initial_messages)
    turns: list[ConversationTurn] = [
        ConversationTurn(role=m["role"], content=m["content"])
        for m in messages
    ]
    all_tools: list[Any] = []
    total_ms: float = 0.0
    reply = ""

    for attempt in range(max(1, max_continuation)):
        if use_stream:
            reply, tools, ms = ask_stream(client, messages, model)
        else:
            reply, tools, ms = ask_chat(client, messages, model)

        all_tools.extend(tools)
        total_ms += ms

        turns.append(ConversationTurn(
            role="assistant",
            content=reply,
            tool_calls=tools,
            latency_ms=ms,
        ))

        # Stop once we have a reply (tool calls are fire-and-forget inside the agent)
        if reply.strip():
            break

        if verbose:
            print(f"  ↻  continuation {attempt + 1} (empty reply, nudging)…")

        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": _CONTINUATION_PROMPT})
        turns.append(ConversationTurn(role="user", content=_CONTINUATION_PROMPT))

    return reply, all_tools, total_ms, turns


# ── LLM judge ─────────────────────────────────────────────────────────────────

@dataclass
class JudgeScore:
    relevance: int = 0
    completeness: int = 0
    accuracy: int = 0
    overall: int = 0
    rationale: str = ""
    error: str = ""


def llm_judge(
    question: str,
    desired_output: str,
    actual_reply: str,
    *,
    judge_model: str | None = None,
    live_data: bool = False,
    no_tools: bool = False,
) -> JudgeScore:
    """Call the LLM judge and return structured scores."""
    if not _JUDGE_API_KEY:
        return JudgeScore(error="JUDGE_API_KEY / OPENAI_API_KEY not set — judge skipped")
    if not desired_output.strip():
        return JudgeScore(error="no reference trajectory for this question")

    try:
        from openai import OpenAI
    except ImportError:
        return JudgeScore(error="openai package not installed")

    model_to_use = judge_model or _JUDGE_MODEL
    client = OpenAI(api_key=_JUDGE_API_KEY, base_url=_JUDGE_BASE_URL)
    user_msg = _JUDGE_USER_TEMPLATE.format(
        desired_output=desired_output,
        actual_reply=actual_reply,
        question=question,
    )
    try:
        response = client.chat.completions.create(
            model=model_to_use,
            messages=[
                {"role": "system", "content": (
                    _JUDGE_SYSTEM_NO_TOOLS if no_tools
                    else _JUDGE_SYSTEM_LIVE_DATA if live_data
                    else _JUDGE_SYSTEM
                )},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=256,
        )
        raw = response.choices[0].message.content or ""
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        # Extract the first balanced {...} block — handles prose preambles,
        # trailing content, "Extra data" errors, and multiple JSON objects.
        start = raw.find("{")
        if start != -1:
            depth, end = 0, start
            for i, ch in enumerate(raw[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            raw = raw[start : end + 1]
        parsed = json.loads(raw)

        def _clamp(v: object) -> int:
            if v is None:
                return 0
            try:
                return max(1, min(5, round(float(str(v)))))
            except (ValueError, TypeError):
                return 0

        return JudgeScore(
            relevance=_clamp(parsed.get("relevance") or parsed.get("Relevance")),
            completeness=_clamp(parsed.get("completeness") or parsed.get("Completeness")),
            accuracy=_clamp(parsed.get("accuracy") or parsed.get("Accuracy")),
            overall=_clamp(parsed.get("overall") or parsed.get("Overall")),
            rationale=str(parsed.get("rationale") or parsed.get("Rationale") or ""),
        )
    except Exception as exc:
        return JudgeScore(error=f"judge error: {exc!r}"[:200])


# ── result record ─────────────────────────────────────────────────────────────

@dataclass
class ConversationTurn:
    role: str
    content: str
    tool_calls: list[Any] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class BenchmarkResult:
    session_id: str
    sheet: str
    category: str
    subcategory: str
    difficulty: str
    question: str
    model: str
    ok: bool
    turns: list[ConversationTurn] = field(default_factory=list)
    reply: str = ""
    tool_call_count: int = 0
    tool_names: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str = ""
    judge: JudgeScore = field(default_factory=JudgeScore)
    judge_skip_reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── runner ────────────────────────────────────────────────────────────────────

def _write_results(
    out_path: Path,
    results: list[BenchmarkResult],
    session_id: str,
    model: str,
    sheet: str,
    judge_model: str | None,
) -> None:
    payload = {
        "session_id": session_id,
        "model": model,
        "sheet": sheet,
        "judge_model": judge_model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": [asdict(r) for r in results],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_benchmark(
    questions: list[BenchmarkQuestion],
    model: str,
    session_id: str,
    *,
    use_stream: bool = False,
    dry_run: bool = False,
    verbose: bool = True,
    enable_judge: bool = True,
    out_path: Path | None = None,
    sheet: str = "both",
    judge_model: str | None = None,
    live_data_judge: bool = False,
    no_tool_requirement: bool = True,
    max_continuation: int = 5,
) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []

    with httpx.Client() as client:
        for i, bq in enumerate(questions, 1):
            tag = f"[{i}/{len(questions)}] [{bq.sheet}] [{bq.difficulty}]"
            if verbose:
                print(f"\n{'─'*70}")
                print(f"{tag}")
                print(f"  {bq.category} > {bq.subcategory}")
                print(f"  Q: {bq.question[:100]}...")

            if dry_run:
                turns = [ConversationTurn(role="user", content=bq.question)]
                results.append(BenchmarkResult(
                    session_id=session_id,
                    sheet=bq.sheet, category=bq.category, subcategory=bq.subcategory,
                    difficulty=bq.difficulty, question=bq.question, model=model,
                    ok=True, reply="[dry-run]", turns=turns,
                ))
                continue

            messages: list[dict[str, str]] = [{"role": "user", "content": bq.question}]

            try:
                reply, tools, ms, turns = ask_until_complete(
                    client, messages, model,
                    use_stream=use_stream,
                    max_continuation=max_continuation,
                    verbose=verbose,
                )

                tool_names = [
                    t.get("tool") or t.get("function", {}).get("name") or ""
                    for t in tools if isinstance(t, dict)
                ]

                judge_score = JudgeScore()
                judge_skip_reason = ""
                if bq.sheet == "Claude-Benchmark":
                    judge_skip_reason = "sheet 2 has no desired_output — judge disabled for this sheet"
                elif bq.sheet == "Extended-Benchmark":
                    judge_skip_reason = _SHEET3_JUDGE_SKIP.get(bq.subcategory, "")
                if enable_judge and bq.desired_output and not judge_skip_reason:
                    if verbose:
                        print("  ⚖  judging…", end=" ", flush=True)
                    is_live = live_data_judge and bq.sheet == "Extended-Benchmark"
                    judge_score = llm_judge(
                        bq.question, bq.desired_output, reply,
                        judge_model=judge_model,
                        live_data=is_live,
                        no_tools=no_tool_requirement,
                    )
                    if verbose:
                        if judge_score.error:
                            print(f"judge error: {judge_score.error}")
                        else:
                            print(
                                f"overall={judge_score.overall}/5  "
                                f"(rel={judge_score.relevance} "
                                f"cmp={judge_score.completeness} "
                                f"acc={judge_score.accuracy})"
                            )
                elif judge_skip_reason and verbose:
                    print(f"  ⚠  judge suppressed — {judge_skip_reason[:80]}")

                result = BenchmarkResult(
                    session_id=session_id,
                    sheet=bq.sheet, category=bq.category, subcategory=bq.subcategory,
                    difficulty=bq.difficulty, question=bq.question, model=model,
                    ok=True, reply=reply[:500], turns=turns,
                    tool_call_count=len(tools),
                    latency_ms=ms, tool_names=tool_names,
                    judge=judge_score,
                    judge_skip_reason=judge_skip_reason,
                )
                if verbose:
                    print(f"  ✓ {ms:.0f}ms | tools={tool_names} | reply={reply[:120]!r}")
            except httpx.HTTPStatusError as exc:
                turns_err = [ConversationTurn(role="user", content=bq.question)]
                result = BenchmarkResult(
                    session_id=session_id,
                    sheet=bq.sheet, category=bq.category, subcategory=bq.subcategory,
                    difficulty=bq.difficulty, question=bq.question, model=model,
                    ok=False,
                    error=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                    turns=turns_err,
                )
                if verbose:
                    print(f"  ✗ HTTP error: {result.error}")
            except Exception as exc:
                turns_err = [ConversationTurn(role="user", content=bq.question)]
                result = BenchmarkResult(
                    session_id=session_id,
                    sheet=bq.sheet, category=bq.category, subcategory=bq.subcategory,
                    difficulty=bq.difficulty, question=bq.question, model=model,
                    ok=False, error=str(exc)[:300],
                    turns=turns_err,
                )
                if verbose:
                    print(f"  ✗ {result.error}")

            results.append(result)
            if out_path is not None and not dry_run:
                _write_results(out_path, results, session_id, model, sheet, judge_model)

    return results


def print_summary(results: list[BenchmarkResult]) -> None:
    print(f"\n{'='*70}")
    print("BENCHMARK SUMMARY")
    ok = [r for r in results if r.ok and not r.error]
    failed = [r for r in results if not r.ok or r.error]
    print(f"  Total: {len(results)} | OK: {len(ok)} | Failed: {len(failed)}")
    if ok:
        avg_ms = sum(r.latency_ms for r in ok) / len(ok)
        avg_tools = sum(r.tool_call_count for r in ok) / len(ok)
        print(f"  Avg latency: {avg_ms:.0f}ms | Avg tool calls: {avg_tools:.1f}")

        judged = [r for r in ok if r.judge.overall > 0]
        if judged:
            avg_overall = sum(r.judge.overall for r in judged) / len(judged)
            avg_rel = sum(r.judge.relevance for r in judged) / len(judged)
            avg_cmp = sum(r.judge.completeness for r in judged) / len(judged)
            avg_acc = sum(r.judge.accuracy for r in judged) / len(judged)
            print(
                f"\n  LLM Judge scores (n={len(judged)}):\n"
                f"    Overall:      {avg_overall:.2f}/5\n"
                f"    Relevance:    {avg_rel:.2f}/5\n"
                f"    Completeness: {avg_cmp:.2f}/5\n"
                f"    Accuracy:     {avg_acc:.2f}/5"
            )

        by_diff: dict[str, list[BenchmarkResult]] = {}
        for r in ok:
            by_diff.setdefault(r.difficulty, []).append(r)
        print("\n  By difficulty:")
        for diff, rr in sorted(by_diff.items()):
            ms = sum(x.latency_ms for x in rr) / len(rr)
            j = [x for x in rr if x.judge.overall > 0]
            judge_str = f" | judge={sum(x.judge.overall for x in j)/len(j):.1f}" if j else ""
            print(f"    {diff:<12} n={len(rr)} avg={ms:.0f}ms{judge_str}")

    judge_skipped = [r for r in results if r.judge_skip_reason]
    if judge_skipped:
        print(f"\n  Judge suppressed ({len(judge_skipped)} cases):")
        for r in judge_skipped:
            label = r.subcategory or r.sheet
            print(f"    [{label}] {r.judge_skip_reason[:90]}")

    if failed:
        print(f"\n  Failed questions:")
        for r in failed:
            print(f"    [{r.sheet}] {r.question[:60]} — {r.error[:80]}")


def _model_slug(model: str) -> str:
    name = model.split("/")[-1] if "/" in model else model
    return re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-")[:40]


def default_out_path(session_id: str, model: str, sheet: str) -> Path:
    slug = _model_slug(model)
    filename = f"{session_id}_{slug}_sheet{sheet}.json"
    return _RESULTS_DIR / filename


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="DojoAgents dashboard benchmark")
    parser.add_argument("--model", default="default",
                        help="Model name to pass in the request (default: 'default')")
    parser.add_argument("--stream", action="store_true", help="Use SSE streaming")
    parser.add_argument("--limit", type=int, default=None, help="Max questions per sheet")
    parser.add_argument("--sheet", choices=["1", "2", "3", "both"], default="both",
                        help="Which benchmark sheet to run (default: both; '3' = extended only)")
    parser.add_argument("--dry-run", action="store_true", help="Print questions without calling API")
    parser.add_argument("--out", default=None,
                        help="Override output path (default: data/benchmark_results/<session>_<model>_sheet<N>.json)")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-question output")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge scoring")
    parser.add_argument(
        "--tool-requirement", action="store_true",
        help=(
            "Judge on tool-call compliance (strict mode). By default the judge scores on "
            "reasoning quality and honest disclosure, which is correct for dashboard agents "
            "that have no market-data tools. Pass this flag only if the agent under test "
            "has full tool access and should be penalised for not calling them."
        ),
    )
    parser.add_argument(
        "--live-data-judge", action="store_true",
        help=(
            "For Extended-Benchmark (sheet 3) questions, replace accuracy scoring with "
            "tool-appropriateness scoring so stale reference values don't unfairly penalise the model."
        ),
    )
    parser.add_argument(
        "--judge-model", default=None,
        help=(
            "Model for the LLM judge (default: JUDGE_MODEL env var, "
            "or claude-haiku-4-5-20251001). Use a *different* model than --model "
            "to avoid self-scoring bias."
        ),
    )
    parser.add_argument("--max-continuation", type=int, default=5,
                        help="Max retries when agent returns empty reply (default: 5)")
    args = parser.parse_args()

    session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    questions: list[BenchmarkQuestion] = []
    if args.sheet in ("1", "both"):
        if not SHEET1_CSV.exists():
            print(f"Sheet 1 CSV not found: {SHEET1_CSV}", file=sys.stderr)
            return 1
        questions += load_sheet1(SHEET1_CSV, args.limit)
    if args.sheet in ("2", "both"):
        if not SHEET2_CSV.exists():
            print(f"Sheet 2 CSV not found: {SHEET2_CSV}", file=sys.stderr)
            return 1
        questions += load_sheet2(SHEET2_CSV, args.limit)
    if args.sheet in ("3", "both"):
        if not SHEET3_CSV.exists():
            print(f"Sheet 3 CSV not found: {SHEET3_CSV}", file=sys.stderr)
            return 1
        questions += load_sheet3(SHEET3_CSV, args.limit)

    print(f"Session: {session_id}")
    print(f"Loaded {len(questions)} questions")
    if not questions:
        print("No questions found — check CSV paths", file=sys.stderr)
        return 1

    model = args.model
    enable_judge = not args.no_judge
    if enable_judge and not _JUDGE_API_KEY:
        print("  [warn] JUDGE_API_KEY / OPENAI_API_KEY not set — LLM judge will be skipped")
        enable_judge = False

    judge_model = (args.judge_model or _JUDGE_MODEL) if enable_judge else None
    mode = "stream" if args.stream else "chat"
    judge_model_label = f"  judge_model={judge_model}" if enable_judge else "  judge=disabled"
    print(f"Endpoint: POST /api/{mode}  |  model={model}{judge_model_label}\n")
    out_path = Path(args.out) if args.out else default_out_path(session_id, model, args.sheet)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Results → {out_path}  (written after each question)\n")

    if args.dry_run:
        for i, bq in enumerate(questions, 1):
            print(f"[{i}/{len(questions)}] [{bq.sheet}] [{bq.difficulty}] {bq.question[:100]}")
        return 0

    results = run_benchmark(
        questions, model, session_id,
        use_stream=args.stream,
        dry_run=False,
        verbose=not args.quiet,
        enable_judge=enable_judge,
        out_path=out_path,
        sheet=args.sheet,
        judge_model=judge_model,
        live_data_judge=args.live_data_judge,
        no_tool_requirement=not args.tool_requirement,
        max_continuation=args.max_continuation,
    )

    print_summary(results)
    print(f"\nResults saved → {out_path}")

    failed = [r for r in results if not r.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
