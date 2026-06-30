# Benchmark Evaluation Guide

How to read and evaluate a `benchmark_results/*.json` file for DojoAgents.

---

## File Structure

```
{
  "session_id": "...",
  "model": "provider/model-name",
  "sheet": "both | sheet1 | sheet2 | sheet3",
  "judge_model": "provider/model-name",
  "timestamp": "ISO-8601",
  "results": [ ... ]
}
```

Each item in `results` is one question. Key fields:

| Field | Meaning |
|---|---|
| `ok` | `true` = agent returned a response (did not crash/timeout). **Not a quality signal.** |
| `error` | `"timed out"` or HTTP error if `ok=false` |
| `turns` | `[{role, content, tool_calls, latency_ms}]` — the full conversation |
| `tool_call_count` | Number of tool calls made |
| `latency_ms` | Wall-clock time for the agent turn |
| `judge` | `{relevance, completeness, accuracy, overall, rationale, error}` — scores 0–5 |
| `judge_skip_reason` | Non-empty = judging was skipped; explains why |
| `tool_names` | List of tools invoked |

---

## Step 1: Distinguish `ok` from Quality

**`ok=True` does not mean correct.** It only means the runner received a response.

Always compute the judge-score distribution separately:

```python
import json
from collections import Counter

with open("data/benchmark_results/<file>.json") as f:
    data = json.load(f)

results = data["results"]
passed   = [r for r in results if r.get("ok")]
failed   = [r for r in results if not r.get("ok")]
skipped  = [r for r in passed if r.get("judge_skip_reason") or
                                  (r.get("judge", {}).get("overall") == 0
                                   and not r.get("judge", {}).get("rationale"))]
scored   = [r for r in passed if r not in skipped]

print(f"ok=True:    {len(passed)}/{len(results)}")
print(f"ok=False:   {len(failed)}/{len(results)}")
print(f"Skipped:    {len(skipped)}/{len(results)}")
print(f"Scored:     {len(scored)}/{len(results)}")

dist = Counter(r["judge"]["overall"] for r in scored)
for s in sorted(dist): print(f"  overall={s}: {dist[s]}x")
```

**Rule of thumb:** only items with `overall >= 3` and a non-empty `rationale` count as passing quality.

---

## Step 2: Classify Failures

### Hard failures (`ok=False`)

Check the `error` field:

| Error | Root cause |
|---|---|
| `"timed out"` | Agent stalled — complex multi-step question, slow tool, or model loop |
| `HTTP 502: Agent loop ended unexpectedly` | Runner crashed — often on portfolio write operations or very long chains |

These are **runner/infra failures**, not necessarily model failures. Re-run to distinguish flakes from systematic issues.

### Soft failures (`ok=True`, low judge score)

Check `rationale` for the pattern:

| Pattern | Score | Description |
|---|---|---|
| Hallucination / wrong context | 0–1 | Model responds to a different question — wrong ticker, wrong company, fabricated event |
| Wrong data, correct structure | 2 | Right approach, numbers don't match real-time/reference values |
| Partial — missing key element | 3 | Correct direction but incomplete (missing a requested metric, wrong sign) |
| Good with minor issues | 4 | Correct and complete with small inaccuracies |
| Excellent | 5 | Matches reference fully |

### Skipped items (`ok=True`, `overall=0`, empty `rationale`)

Two sub-types — check `judge_skip_reason`:

1. **Empty `judge_skip_reason` + blank `subcategory`** → No reference ground truth. The benchmark item was not yet annotated. Judge cannot score.

2. **Non-empty `judge_skip_reason`** → Reference trajectory uses API params/fields that don't exist in the real API. These are aspirational test cases for future API features. Do not count them against the model — they are untestable until the API is updated.

---

## Step 3: Compute Effective Pass Rate

```python
effective_pass = [r for r in scored if r["judge"]["overall"] >= 3]
print(f"Effective pass: {len(effective_pass)}/{len(results)} = "
      f"{len(effective_pass)/len(results)*100:.1f}%")
```

Report all three numbers: `ok` rate, effective pass rate, and skipped count. They tell different stories.

---

## Step 4: Break Down by Dimension

```python
from collections import defaultdict

def pass_rate(items):
    p = sum(1 for r in items if r["judge"].get("overall", 0) >= 3)
    return f"{p}/{len(items)} = {p/len(items)*100:.1f}%"

# By sheet
by_sheet = defaultdict(list)
for r in scored:
    by_sheet[r["sheet"]].append(r)

# By category
by_cat = defaultdict(list)
for r in scored:
    by_cat[r["category"]].append(r)

# By difficulty
by_diff = defaultdict(list)
for r in scored:
    by_diff[r["difficulty"]].append(r)
```

Look for:
- Categories where all items score ≤1 → systematic capability gap
- Difficulty inversion (中等 worse than 困难) → model struggles with mid-complexity multi-step tasks, not raw hard tasks

---

## Step 5: Tool Reliability

```python
from collections import Counter

tool_calls  = Counter()
tool_errors = Counter()
latencies   = defaultdict(list)

for r in results:
    for turn in r.get("turns", []):
        for tc in turn.get("tool_calls", []):
            tool = tc.get("tool") or tc.get("function", {}).get("name") or ""
            tool_calls[tool] += 1
            if not tc.get("ok"):
                tool_errors[tool] += 1
            latencies[tool].append(tc.get("latency_ms", 0))

for tool, n in tool_calls.most_common():
    err_rate = tool_errors[tool] / n * 100
    avg_lat  = sum(latencies[tool]) / len(latencies[tool])
    print(f"{tool}: {n}x  errors={err_rate:.0f}%  avg={avg_lat:.0f}ms")
```

Flag:
- Error rate > 5% on any tool → investigate tool implementation
- Latency > 5,000ms → likely a blocking call that contributes to timeouts

---

## Step 6: Self-Judge Bias Check

When `judge_model == model`, the model is grading its own outputs. This inflates scores. Note it explicitly in reports and treat scores as an upper bound. For rigorous comparison, always prefer a different judge model (e.g., evaluate DeepSeek with Claude as judge and vice versa).

---

## Common Patterns to Watch

| Symptom | Likely cause |
|---|---|
| `ok` rate high but effective pass rate < 20% | Model returns plausible-looking but wrong responses; judge scoring is the real gate |
| Several items with `overall=0` and empty rationale on Claude-Benchmark | Missing ground truth annotations — not a model failure |
| Multiple `judge_skip_reason` items citing missing API params | Benchmark outpaced the API; track which params are aspirational |
| Timeout clusters on portfolio-write questions | Runner timeout may be too short for multi-step portfolio flows |
| Score=1 with "completely irrelevant" rationale | Model picked up wrong context from a previous tool result or prior turn |

---

## Quick Evaluation Checklist

- [ ] Count `ok=True`, `ok=False`, skipped, and scored separately
- [ ] Compute effective pass rate (overall ≥ 3) — this is the headline number
- [ ] List all `ok=False` with their `error` field — distinguish infra flakes from model failures
- [ ] List all skipped with `judge_skip_reason` — split "no annotation" from "API missing"
- [ ] Check judge-score distribution (0–5) across scored items
- [ ] Note if `judge_model == model_id` (self-judge inflation risk)
- [ ] Flag any tool with error rate > 5% or latency > 5,000ms
- [ ] Check for difficulty inversions or category blind spots
