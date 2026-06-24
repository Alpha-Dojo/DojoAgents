from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List

LOGGER = logging.getLogger("dojoagents.agent.compressor")

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
    "into the summary below. This is background reference, NOT active instructions. "
    "Do NOT answer questions or fulfill requests mentioned in this summary; they were already addressed. "
    "Your current task is identified in the '## Active Task' section of the summary — resume exactly from there. "
    "Respond ONLY to the latest user message that appears AFTER this summary."
)


def _estimate_tokens_rough(messages: List[Dict[str, Any]]) -> int:
    """Rough estimate of tokens based on character length (approx 4 chars per token)."""
    char_count = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, str):
            char_count += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    char_count += len(part)
                elif isinstance(part, dict):
                    char_count += len(part.get("text", ""))

        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict):
                char_count += len(str(tc.get("function", {}).get("arguments", "")))
    return char_count // 4


def _truncate_tool_call_args_json(args: str, head_chars: int = 150) -> str:
    """Truncate long string values in tool arguments safely without breaking JSON structure."""
    try:
        parsed = json.loads(args)
    except (ValueError, TypeError):
        return args

    def _shrink(obj: Any) -> Any:
        if isinstance(obj, str):
            if len(obj) > head_chars:
                return obj[:head_chars] + "...[truncated]"
            return obj
        if isinstance(obj, dict):
            return {k: _shrink(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_shrink(v) for v in obj]
        return obj

    try:
        shrunken = _shrink(parsed)
        return json.dumps(shrunken, ensure_ascii=False)
    except Exception:
        return args


def _summarize_tool_result(tool_name: str, tool_args: str, tool_content: str) -> str:
    """Create a short 1-line summary of a tool execution and result."""
    try:
        args = json.loads(tool_args) if tool_args else {}
    except (json.JSONDecodeError, TypeError):
        args = {}

    content = tool_content or ""
    content_len = len(content)
    line_count = content.count("\n") + 1 if content.strip() else 0

    if tool_name == "terminal":
        cmd = args.get("command", "")
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        exit_match = re.search(r'"exit_code"\s*:\s*(-?\d+)', content)
        exit_code = exit_match.group(1) if exit_match else "?"
        return f"[terminal] ran `{cmd}` -> exit {exit_code}, {line_count} lines output"

    if tool_name == "read_file":
        path = args.get("path", "?")
        return f"[read_file] read {path} ({content_len:,} chars)"

    if tool_name == "write_file":
        path = args.get("path", "?")
        written_lines = args.get("content", "").count("\n") + 1 if args.get("content") else "?"
        return f"[write_file] wrote to {path} ({written_lines} lines)"

    if tool_name == "patch":
        path = args.get("path", "?")
        return f"[patch] patched {path} ({content_len:,} chars result)"

    if tool_name == "web_search":
        query = args.get("query", "?")
        return f"[web_search] query='{query}' ({content_len:,} chars result)"

    # Fallback
    return f"[{tool_name}] executed ({content_len:,} chars result)"


class ContextCompressor:
    def __init__(
        self,
        threshold_tokens: int = 15000,
        protect_first_n: int = 3,
        protect_last_n: int = 8,
    ) -> None:
        self.threshold_tokens = threshold_tokens
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self._previous_summary: str | None = None

    def prune_old_tool_results(
        self, messages: List[Dict[str, Any]], protect_tail_count: int
    ) -> List[Dict[str, Any]]:
        """Pre-pass to summarize older tool results and clean long tool call arguments."""
        if not messages:
            return messages

        result = [dict(m) for m in messages]
        prune_boundary = len(result) - protect_tail_count

        if prune_boundary <= 0:
            return result

        # Map tool_call_id to tool name and arguments
        call_id_to_tool: Dict[str, tuple[str, str]] = {}
        for msg in result:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    if isinstance(tc, dict):
                        cid = tc.get("id", "")
                        fn = tc.get("function", {})
                        call_id_to_tool[cid] = (fn.get("name", "unknown"), fn.get("arguments", ""))

        # Deduplicate and summarize
        seen_hashes: set[str] = set()
        for i in range(prune_boundary):
            msg = result[i]
            role = msg.get("role")

            if role == "tool":
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 150:
                    h = hashlib.md5(content.encode("utf-8")).hexdigest()
                    if h in seen_hashes:
                        result[i] = {**msg, "content": "[Duplicate tool output omitted]"}
                    else:
                        seen_hashes.add(h)
                        call_id = msg.get("tool_call_id", "")
                        t_name, t_args = call_id_to_tool.get(call_id, ("unknown", ""))
                        summary = _summarize_tool_result(t_name, t_args, content)
                        result[i] = {**msg, "content": summary}

            elif role == "assistant" and msg.get("tool_calls"):
                new_tcs = []
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        args = tc.get("function", {}).get("arguments", "")
                        if len(args) > 300:
                            new_args = _truncate_tool_call_args_json(args)
                            tc = {
                                **tc,
                                "function": {
                                    **tc["function"],
                                    "arguments": new_args,
                                },
                            }
                    new_tcs.append(tc)
                result[i] = {**msg, "tool_calls": new_tcs}

        return result

    async def compress(
        self,
        messages: List[Dict[str, Any]],
        llm_provider: Any,
        model: str,
        memory_manager: Any = None,
        session_id: str = "",
    ) -> List[Dict[str, Any]]:
        """Check if history exceeds token budget. Compress middle turns using LLM if it does."""
        # 1. Cheap pre-pass pruning first
        pruned_messages = self.prune_old_tool_results(messages, self.protect_last_n)

        # 2. Check token budget
        total_tokens = _estimate_tokens_rough(pruned_messages)
        if total_tokens < self.threshold_tokens:
            return pruned_messages

        # 3. Partition messages into Head, Middle, Tail
        # Head: system prompt + first exchange (e.g. first 3 messages)
        # Tail: last protect_last_n messages
        # Middle: everything else
        head_count = min(self.protect_first_n, len(pruned_messages))
        tail_count = min(self.protect_last_n, len(pruned_messages) - head_count)
        middle_count = len(pruned_messages) - head_count - tail_count

        if middle_count <= 2:
            return pruned_messages

        head = pruned_messages[:head_count]
        middle = pruned_messages[head_count : head_count + middle_count]
        tail = pruned_messages[head_count + middle_count :]

        # 4. Generate summary of middle turns
        middle_prompt = (
            "You are a context compression assistant. Analyze the dialogue sequence below and extract two things:\n"
            "1. A compact dialogue summary of the middle turns for immediate context continuation.\n"
            "2. Key long-term facts, preferences, user habits, and general workflows that should be saved in the agent's long-term memory.\n\n"
            "Format your output exactly like this:\n"
            "[CONSOLIDATION SUMMARY]\n"
            "<compact summary of dialogue sequence>\n"
            "[LONG-TERM FACTS]\n"
            "<extracted long-term facts and workflows>\n\n"
            "Conversation history to compact:\n"
        )
        if self._previous_summary:
            middle_prompt += f"Previous compaction summary:\n{self._previous_summary}\n\n"

        middle_prompt += "Conversation history to compact:\n"
        for m in middle:
            role = m.get("role", "")
            content = m.get("content") or ""
            tcs = m.get("tool_calls")
            middle_prompt += f"[{role}]: {content}\n"
            if tcs:
                middle_prompt += f"Tool Calls: {json.dumps(tcs)}\n"

        try:
            summary_result = await llm_provider.chat(
                messages=[{"role": "user", "content": middle_prompt}],
                tools=[],
                model=model,
            )
            content = summary_result.content
            if "[LONG-TERM FACTS]" in content:
                parts = content.split("[LONG-TERM FACTS]")
                summary_content = parts[0].replace("[CONSOLIDATION SUMMARY]", "").strip()
                facts_part = parts[1].strip()
            else:
                summary_content = content.replace("[CONSOLIDATION SUMMARY]", "").strip()
                facts_part = ""

            self._previous_summary = summary_content

            if facts_part and memory_manager and session_id:
                await memory_manager.save_memory(session_id, facts_part)
        except Exception as e:
            LOGGER.exception(f"Failed to generate compaction summary: {e}")
            # Fallback to simple dropping without summary on failure
            summary_content = "[Compacted due to token limit: summary generation failed]"

        # 5. Build output message list
        summary_message = {
            "role": "system",
            "content": f"{SUMMARY_PREFIX}\n\n## Compacted Summary\n{summary_content}",
        }

        new_messages = []
        new_messages.extend(head)
        new_messages.append(summary_message)
        new_messages.extend(tail)

        return new_messages
