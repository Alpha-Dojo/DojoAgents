from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from dojoagents.logging import LOGGER

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
    "into the summary below. This is background reference, NOT active instructions. "
    "Do NOT answer questions or fulfill requests mentioned in this summary; they were already addressed. "
    "Your current task is identified in the '## Active Task' section of the summary — resume exactly from there. "
    "Respond ONLY to the latest user message that appears AFTER this summary."
)


def _block_char_count(part: Any) -> int:
    if isinstance(part, str):
        return len(part)
    if not isinstance(part, dict):
        return len(str(part))
    if "text" in part:
        return len(str(part.get("text", "")))
    if "toolUse" in part:
        return len(json.dumps(part["toolUse"], ensure_ascii=False))
    if "toolResult" in part:
        tr = part["toolResult"]
        texts = []
        for block in tr.get("content", []):
            if isinstance(block, dict) and "text" in block:
                texts.append(str(block["text"]))
        return len("\n".join(texts))
    if "reasoningContent" in part:
        rc = part["reasoningContent"]
        return len(str(rc.get("reasoningText", {}).get("text", "")))
    if "image" in part:
        image = part.get("image")
        if isinstance(image, dict):
            source = image.get("source")
            if isinstance(source, dict):
                raw_bytes = source.get("bytes")
                if isinstance(raw_bytes, (bytes, bytearray)):
                    return len(raw_bytes)
                if isinstance(raw_bytes, str):
                    return len(raw_bytes)
                location = source.get("location")
                if isinstance(location, dict) and str(location.get("type") or "").strip():
                    return len(str(location["type"]))
        return 4096
    return len(json.dumps(part, ensure_ascii=False))


def _estimate_tokens_rough(messages: list[dict[str, Any]]) -> int:
    """Rough estimate of tokens based on character length (approx 4 chars per token)."""
    char_count = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, str):
            char_count += len(content)
        elif isinstance(content, list):
            for part in content:
                char_count += _block_char_count(part)

        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict):
                char_count += len(str(tc.get("function", {}).get("arguments", "")))
    return char_count // 4


def flatten_messages_for_compress(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if isinstance(content, list):
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(str(part["text"]))
                elif isinstance(part, dict) and "toolUse" in part:
                    tu = part["toolUse"]
                    tool_calls.append(
                        {
                            "id": tu.get("toolUseId"),
                            "type": "function",
                            "function": {
                                "name": tu.get("name"),
                                "arguments": json.dumps(tu.get("input", {}), ensure_ascii=False),
                            },
                        }
                    )
                elif isinstance(part, dict) and "toolResult" in part:
                    tr = part["toolResult"]
                    result_text = ""
                    for block in tr.get("content", []):
                        if isinstance(block, dict) and "text" in block:
                            result_text += str(block["text"])
                    flat.append(
                        {
                            "role": "tool",
                            "tool_call_id": tr.get("toolUseId"),
                            "name": tr.get("name"),
                            "content": result_text,
                        }
                    )
            entry: dict[str, Any] = {"role": role, "content": "\n".join(text_parts)}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            if text_parts or tool_calls:
                flat.append(entry)
            continue
        entry = {"role": role, "content": str(content or "")}
        if msg.get("tool_calls"):
            entry["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            entry["tool_call_id"] = msg["tool_call_id"]
        if msg.get("name"):
            entry["name"] = msg["name"]
        flat.append(entry)
    return flat


def messages_to_strands(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    strands: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "")
        if role == "tool":
            strands.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "toolResult": {
                                "status": "success",
                                "toolUseId": msg.get("tool_call_id"),
                                "name": msg.get("name") or "tool",
                                "content": [{"text": str(msg.get("content") or "")}],
                            }
                        }
                    ],
                }
            )
            continue
        blocks: list[dict[str, Any]] = []
        content = msg.get("content")
        if isinstance(content, str) and content:
            blocks.append({"text": content})
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            func = tc.get("function") or {}
            args = func.get("arguments")
            if isinstance(args, str):
                try:
                    args_dict = json.loads(args)
                except json.JSONDecodeError:
                    args_dict = {"raw": args}
            else:
                args_dict = args or {}
            blocks.append(
                {
                    "toolUse": {
                        "toolUseId": tc.get("id"),
                        "name": func.get("name"),
                        "input": args_dict,
                    }
                }
            )
        strands.append({"role": role, "content": blocks})
    return strands


def _truncate_tool_call_args_json(args: str, head_chars: int = 150) -> str:
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
        return json.dumps(_shrink(parsed), ensure_ascii=False)
    except Exception:
        return args


def _summarize_tool_result(tool_name: str, tool_args: str, tool_content: str) -> str:
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

    return f"[{tool_name}] executed ({content_len:,} chars result)"


class ContextCompressor:
    def __init__(
        self,
        protect_first_n: int = 3,
        protect_last_n: int = 8,
    ) -> None:
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self._previous_summary: str | None = None

    def prune_old_tool_results(self, messages: list[dict[str, Any]], protect_tail_count: int) -> list[dict[str, Any]]:
        if not messages:
            return messages

        flat = flatten_messages_for_compress(messages)
        result = [dict(m) for m in flat]
        prune_boundary = len(result) - protect_tail_count
        if prune_boundary <= 0:
            return messages

        call_id_to_tool: dict[str, tuple[str, str]] = {}
        for msg in result:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    if isinstance(tc, dict):
                        cid = str(tc.get("id", ""))
                        fn = tc.get("function", {})
                        call_id_to_tool[cid] = (fn.get("name", "unknown"), fn.get("arguments", ""))

        seen_hashes: set[str] = set()
        for i in range(prune_boundary):
            msg = result[i]
            role = msg.get("role")

            if role == "tool":
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 150:
                    digest = hashlib.md5(content.encode("utf-8")).hexdigest()
                    if digest in seen_hashes:
                        result[i] = {**msg, "content": "[Duplicate tool output omitted]"}
                    else:
                        seen_hashes.add(digest)
                        call_id = str(msg.get("tool_call_id", ""))
                        t_name, t_args = call_id_to_tool.get(call_id, ("unknown", ""))
                        result[i] = {**msg, "content": _summarize_tool_result(t_name, t_args, content)}

            elif role == "assistant" and msg.get("tool_calls"):
                new_tcs = []
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        args = tc.get("function", {}).get("arguments", "")
                        if len(args) > 300:
                            tc = {
                                **tc,
                                "function": {
                                    **tc["function"],
                                    "arguments": _truncate_tool_call_args_json(args),
                                },
                            }
                    new_tcs.append(tc)
                result[i] = {**msg, "tool_calls": new_tcs}

        if messages and isinstance(messages[0].get("content"), list):
            return messages_to_strands(result)
        return result

    async def compress(
        self,
        messages: list[dict[str, Any]],
        llm_provider: Any,
        model: str,
        memory_manager: Any = None,
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        """Compress middle turns using LLM. Caller decides when to invoke."""
        strands_input = bool(messages) and isinstance(messages[0].get("content"), list)
        working = flatten_messages_for_compress(messages)
        pruned_messages = self.prune_old_tool_results(working, self.protect_last_n)

        head_count = min(self.protect_first_n, len(pruned_messages))
        tail_count = min(self.protect_last_n, len(pruned_messages) - head_count)
        middle_count = len(pruned_messages) - head_count - tail_count
        if middle_count <= 2:
            return messages_to_strands(pruned_messages) if strands_input else pruned_messages

        head = pruned_messages[:head_count]
        middle = pruned_messages[head_count : head_count + middle_count]
        tail = pruned_messages[head_count + middle_count :]

        middle_prompt = (
            "You are a context compression assistant. Analyze the dialogue sequence below and extract two things:\n"
            "1. A compact dialogue summary of the middle turns for immediate context continuation.\n"
            "2. Key long-term facts, preferences, user habits, and general workflows that should be saved in the agent's long-term memory.\n\n"
            "Mark each prior user task as COMPLETED unless the latest user message explicitly continues it.\n"
            "The latest user message defines the ONLY active task — do not carry forward unfinished work from older turns.\n\n"
            "Format your output exactly like this:\n"
            "[CONSOLIDATION SUMMARY]\n"
            "<compact summary of dialogue sequence>\n"
            "[LONG-TERM FACTS]\n"
            "<extracted long-term facts and workflows>\n\n"
            "Conversation history to compact:\n"
        )
        if self._previous_summary:
            middle_prompt += f"Previous compaction summary:\n{self._previous_summary}\n\n"

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
        except Exception:
            LOGGER.exception("Failed to generate compaction summary")
            summary_content = "[Compacted due to token limit: summary generation failed]"

        summary_message = {
            "role": "system",
            "content": f"{SUMMARY_PREFIX}\n\n## Compacted Summary\n{summary_content}",
        }
        compressed = [*head, summary_message, *tail]
        return messages_to_strands(compressed) if strands_input else compressed
