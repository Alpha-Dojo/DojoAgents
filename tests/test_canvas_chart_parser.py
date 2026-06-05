"""Tests for DOJO_CHART block parser protocol.

The DOJO_CHART protocol is a text-based rendering protocol where the Agent embeds
chart data and ECharts rendering scripts inside fenced code blocks tagged ``DOJO_CHART``.
The frontend ``useChat()`` composable extracts these blocks from the streaming text
and sends them to the Canvas iframe for rendering.

These Python tests validate the protocol regex and JSON extraction logic, serving as
the canonical specification that the TypeScript implementation must match.
"""
from __future__ import annotations

import json
import re
import pytest

# ---------------------------------------------------------------------------
# Protocol constants (must match frontend src/utils/chartParser.ts)
# ---------------------------------------------------------------------------
CHART_RE = re.compile(r"```DOJO_CHART\n([\s\S]*?)\n```")


def extract_dojo_chart(text: str) -> dict | None:
    """Extract and parse the first DOJO_CHART block from *text*.

    Returns ``{"data": ..., "script": ...}`` on success, or ``None``.
    """
    m = CHART_RE.search(text)
    if not m:
        return None
    try:
        payload = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


# ---------------------------------------------------------------------------
# Tests: valid DOJO_CHART block extraction
# ---------------------------------------------------------------------------

class TestExtractValidBlock:
    def test_basic_kline_block(self):
        payload = json.dumps({
            "data": [{"time": 1700000000, "open": 189.5, "high": 191.2,
                      "low": 188.8, "close": 190.6, "volume": 52000000}],
            "script": "chart.setOption({series: [{type: 'candlestick'}]});"
        })
        text = (
            "Here is the AAPL K-line chart:\n"
            "```DOJO_CHART\n"
            f"{payload}"
            "\n```\n"
            "The chart shows an upward trend."
        )
        result = extract_dojo_chart(text)
        assert result is not None
        assert "data" in result
        assert "script" in result
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 1
        assert result["data"][0]["open"] == 189.5

    def test_block_at_start_of_text(self):
        text = (
            "```DOJO_CHART\n"
            '{"data": [1, 2, 3], "script": "console.log(data);"}'
            "\n```\n"
            "Some explanation after."
        )
        result = extract_dojo_chart(text)
        assert result is not None
        assert result["data"] == [1, 2, 3]

    def test_block_at_end_of_text(self):
        text = (
            "Some explanation before.\n"
            "```DOJO_CHART\n"
            '{"data": [], "script": ""}'
            "\n```"
        )
        result = extract_dojo_chart(text)
        assert result is not None
        assert result["data"] == []

    def test_block_with_complex_script(self):
        script = (
            "chart.setOption({\n"
            "  title: { text: 'BTC K-Line' },\n"
            "  tooltip: { trigger: 'axis' },\n"
            "  xAxis: { data: data.map(d => new Date(d.time*1000).toLocaleDateString()) },\n"
            "  yAxis: { scale: true },\n"
            "  series: [{ type: 'candlestick', data: data.map(d => [d.open, d.close, d.low, d.high]) }]\n"
            "});"
        )
        payload = json.dumps({"data": [{"time": 1, "open": 1, "high": 2, "low": 0, "close": 1.5}], "script": script})
        text = f"```DOJO_CHART\n{payload}\n```"
        result = extract_dojo_chart(text)
        assert result is not None
        assert "chart.setOption" in result["script"]

    def test_empty_data_array(self):
        text = "```DOJO_CHART\n" + json.dumps({"data": [], "script": ""}) + "\n```"
        result = extract_dojo_chart(text)
        assert result is not None
        assert result["data"] == []
        assert result["script"] == ""


# ---------------------------------------------------------------------------
# Tests: no match scenarios
# ---------------------------------------------------------------------------

class TestNoMatch:
    def test_plain_text_no_block(self):
        assert extract_dojo_chart("Just a normal response with no chart.") is None

    def test_partial_block_no_closing(self):
        """During streaming, the closing ``` may not have arrived yet."""
        text = "```DOJO_CHART\n" + '{"data": [], "script": ""}'
        assert extract_dojo_chart(text) is None

    def test_wrong_language_tag(self):
        text = "```json\n" + '{"data": [], "script": ""}' + "\n```"
        assert extract_dojo_chart(text) is None

    def test_empty_string(self):
        assert extract_dojo_chart("") is None

    def test_only_opening_fence(self):
        assert extract_dojo_chart("```DOJO_CHART\n") is None


# ---------------------------------------------------------------------------
# Tests: invalid JSON handling
# ---------------------------------------------------------------------------

class TestInvalidJSON:
    def test_malformed_json_returns_none(self):
        text = "```DOJO_CHART\n" + "{invalid json here}" + "\n```"
        assert extract_dojo_chart(text) is None

    def test_truncated_json_returns_none(self):
        text = "```DOJO_CHART\n" + '{"data": [1, 2' + "\n```"
        assert extract_dojo_chart(text) is None

    def test_json_array_not_object(self):
        """Top-level array is not a valid DOJO_CHART payload."""
        text = "```DOJO_CHART\n" + "[1, 2, 3]" + "\n```"
        assert extract_dojo_chart(text) is None

    def test_json_string_not_object(self):
        text = "```DOJO_CHART\n" + '"just a string"' + "\n```"
        assert extract_dojo_chart(text) is None


# ---------------------------------------------------------------------------
# Tests: multiple blocks
# ---------------------------------------------------------------------------

class TestMultipleBlocks:
    def test_first_block_extracted(self):
        block1 = json.dumps({"data": [1], "script": "s1"})
        block2 = json.dumps({"data": [2], "script": "s2"})
        text = f"```DOJO_CHART\n{block1}\n```\nSome text\n```DOJO_CHART\n{block2}\n```"
        result = extract_dojo_chart(text)
        assert result is not None
        assert result["data"] == [1]
        assert result["script"] == "s1"


# ---------------------------------------------------------------------------
# Tests: embedded in markdown
# ---------------------------------------------------------------------------

class TestEmbeddedInMarkdown:
    def test_block_between_paragraphs(self):
        payload = json.dumps({"data": [{"v": 42}], "script": "fn()"})
        text = (
            "# Analysis Report\n\n"
            "Here is the chart:\n\n"
            f"```DOJO_CHART\n{payload}\n```\n\n"
            "## Summary\n"
            "The data shows strong performance."
        )
        result = extract_dojo_chart(text)
        assert result is not None
        assert result["data"][0]["v"] == 42

    def test_block_after_code_block(self):
        """A normal code block before DOJO_CHART should not interfere."""
        payload = json.dumps({"data": [], "script": ""})
        text = (
            "```python\nprint('hello')\n```\n\n"
            f"```DOJO_CHART\n{payload}\n```"
        )
        result = extract_dojo_chart(text)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: canvas-chart skill discovery (backend)
# ---------------------------------------------------------------------------

class TestCanvasChartSkillDiscovery:
    """Verify the canvas-chart skill is discoverable by the skill system."""

    def test_skill_directory_exists(self):
        from pathlib import Path
        skill_dir = Path(__file__).parent.parent / "dojoagents" / "skills" / "built_in" / "canvas-chart"
        assert skill_dir.is_dir(), f"canvas-chart skill directory not found: {skill_dir}"

    def test_skill_md_exists(self):
        from pathlib import Path
        skill_md = Path(__file__).parent.parent / "dojoagents" / "skills" / "built_in" / "canvas-chart" / "SKILL.md"
        assert skill_md.is_file(), f"SKILL.md not found: {skill_md}"

    def test_skill_has_valid_frontmatter(self):
        from pathlib import Path
        skill_md = Path(__file__).parent.parent / "dojoagents" / "skills" / "built_in" / "canvas-chart" / "SKILL.md"
        content = skill_md.read_text()
        assert content.startswith("---"), "SKILL.md must start with frontmatter ---"
        # Extract frontmatter
        parts = content.split("---", 2)
        assert len(parts) >= 3, "SKILL.md must have closing ---"
        fm = parts[1]
        assert "name: canvas-chart" in fm, "Frontmatter must declare name: canvas-chart"
        assert "description:" in fm, "Frontmatter must have description"

    def test_skill_contains_dojo_chart_protocol(self):
        from pathlib import Path
        skill_md = Path(__file__).parent.parent / "dojoagents" / "skills" / "built_in" / "canvas-chart" / "SKILL.md"
        content = skill_md.read_text()
        assert "DOJO_CHART" in content, "Skill must document the DOJO_CHART protocol"
        assert "```DOJO_CHART" in content, "Skill must include DOJO_CHART example"

    def test_skill_contains_echarts_templates(self):
        from pathlib import Path
        skill_md = Path(__file__).parent.parent / "dojoagents" / "skills" / "built_in" / "canvas-chart" / "SKILL.md"
        content = skill_md.read_text()
        assert "candlestick" in content.lower() or "k-line" in content.lower() or "kline" in content.lower(), \
            "Skill must include K-line/candlestick template"
        assert "chart.setOption" in content, "Skill must show chart.setOption usage"
