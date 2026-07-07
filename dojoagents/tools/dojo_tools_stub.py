from __future__ import annotations

import re
from typing import Iterable

HERMES_INTERNAL_LOAD_TOOL = "__dojo_load_tool_result__"
HERMES_INTERNAL_LIST_TOOLS = "__dojo_list_tool_results__"

HERMES_RPC_BLOCKED_TOOLS = frozenset(
    {
        "execute_code",
        "code_execution",
    }
)

# Tools with positional-arg convenience wrappers — skip auto-generated duplicates.
HERMES_CONVENIENCE_TOOLS = frozenset(
    {
        "terminal",
        "read_file",
        "write_session_file",
    }
)


def hermes_function_name(tool_name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name)
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        safe = "tool"
    if safe[0].isdigit():
        safe = f"tool_{safe}"
    return safe


def iter_hermes_exposed_tools(tool_names: Iterable[str]) -> list[str]:
    names = sorted({name for name in tool_names if name and name not in HERMES_RPC_BLOCKED_TOOLS and name not in HERMES_CONVENIENCE_TOOLS})
    used: set[str] = set()
    exposed: list[str] = []
    for name in names:
        fn = hermes_function_name(name)
        if fn in used:
            fn = f"{fn}_{abs(hash(name)) % 10_000}"
        used.add(fn)
        exposed.append(name)
    return exposed


def build_dojo_tools_stub_code(*, socket_path: str, tool_names: Iterable[str]) -> str:
    exposed = iter_hermes_exposed_tools(tool_names)
    fn_by_tool = {}
    used_names: set[str] = set()
    for name in exposed:
        fn = hermes_function_name(name)
        if fn in used_names:
            fn = f"{fn}_{abs(hash(name)) % 10_000}"
        used_names.add(fn)
        fn_by_tool[name] = fn

    function_blocks: list[str] = []
    for name in exposed:
        fn = fn_by_tool[name]
        function_blocks.append(
            f"def {fn}(args=None, **kwargs):\n" f"    payload = dict(args or {{}})\n" f"    payload.update(kwargs)\n" f"    return _rpc_call({name!r}, payload)\n"
        )

    return f'''"""Auto-generated RPC bridge to DojoAgents tools for execute_code."""
import json
import os
import socket
import sys

_SOCKET_PATH = {socket_path!r}


def _read_response(sock):
    chunks = []
    total = 0
    max_size = 32 * 1024 * 1024
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_size:
            raise ValueError("execute_code RPC response exceeds 32 MiB")
        joined = b"".join(chunks)
        if b"\\n" in joined:
            break
    return joined.split(b"\\n", 1)[0].decode("utf-8")


def _write_session_file_local(filename, content, format="text", append=False):
    import json

    sessions_root = os.environ.get("DOJO_SESSIONS_ROOT")
    session_id = os.environ.get("DOJO_SESSION_ID")
    if not sessions_root or not session_id:
        return None

    try:
        from dojoagents.tools.session_file_tool import write_session_file
    except ModuleNotFoundError:
        return None

    payload = write_session_file(
        sessions_root=sessions_root,
        session_id=session_id,
        filename=filename,
        content=content,
        fmt=format,
        append=append,
    )
    res = {{
        "ok": True,
        "content": json.dumps(payload, ensure_ascii=False),
        "data": payload,
        "error": None,
    }}
    _record_session_output(payload)
    return res


def _record_session_output(payload):
    manifest = os.environ.get("DOJO_SESSION_OUTPUT_MANIFEST")
    if not manifest or not isinstance(payload, dict):
        return
    entry = {{
        "filename": payload.get("filename"),
        "path": payload.get("path"),
        "bytes_written": payload.get("bytes_written"),
        "output_dir": payload.get("output_dir"),
    }}
    if not entry.get("filename") or not entry.get("path"):
        return
    with open(manifest, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\\n")


def _rpc_call(tool_name, args):
    payload = {{"tool": tool_name, "args": args or {{}}}}
    if sys.platform == "win32":
        import dojoagents.tools.af_unix_asyncio_compat as sync_unix
        with sync_unix.create_connection(_SOCKET_PATH) as sock:
            sock.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\\n")
            raw = _read_response(sock)
    else:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(_SOCKET_PATH)
            sock.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\\n")
            raw = _read_response(sock)
    if not raw.strip():
        return {{"ok": False, "content": "", "error": "empty RPC response"}}
    return json.loads(raw)


def call_tool(name, args=None, **kwargs):
    payload = dict(args or {{}})
    payload.update(kwargs)
    return _rpc_call(name, payload)


def load_tool_result(call_id):
    return _rpc_call({HERMES_INTERNAL_LOAD_TOOL!r}, {{"call_id": call_id}})


def list_tool_results():
    return _rpc_call({HERMES_INTERNAL_LIST_TOOLS!r}, {{}})


{"".join(function_blocks)}

def terminal(command):
    return _rpc_call("terminal", {{"command": command}})


def read_file(path, offset=1, limit=500):
    return _rpc_call("read_file", {{"path": path, "offset": offset, "limit": limit}})


def write_session_file(filename, content, format="text", append=False):
    local = _write_session_file_local(filename, content, format=format, append=append)
    if local is not None:
        return local
    res = _rpc_call(
        "write_session_file",
        {{
            "filename": filename,
            "content": content,
            "format": format,
            "append": append,
        }},
    )
    data = res.get("data")
    if isinstance(data, dict):
        _record_session_output(data)
    else:
        content_text = res.get("content")
        if isinstance(content_text, str) and content_text.strip().startswith("{{"):
            try:
                _record_session_output(json.loads(content_text))
            except json.JSONDecodeError:
                pass
    return res


def tool_json(res):
    if not isinstance(res, dict):
        raise TypeError("tool response must be a dict")
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or "tool call failed")
    data = res.get("data")
    if isinstance(data, dict):
        return data
    content = res.get("content")
    if isinstance(content, str) and content.strip().startswith(("{{", "[")):
        return json.loads(content)
    return res


def tool_rows(res, key=None):
    """Return tabular rows — delegates to schema-driven tool_table when available."""
    hint = res.get("schema_hint") if isinstance(res, dict) else None
    if key is None and isinstance(hint, dict) and hint.get("tables") and hint.get("default_table"):
        return tool_table(res)
    data = tool_json(res)
    hint_key = hint.get("rows_key") if isinstance(hint, dict) else None
    fallback_keys = hint.get("fallback_rows_keys") if isinstance(hint, dict) else None
    if key:
        rows = data.get(key)
        if isinstance(rows, list):
            return rows
        raise KeyError(f"list key not found: {{key!r}}")
    candidates = []
    if hint_key:
        candidates.append(hint_key)
    if isinstance(fallback_keys, list):
        candidates.extend(str(item) for item in fallback_keys if item)
    candidates.extend(["klines", "bars", "items", "rows", "positions", "holdings", "candidates"])
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        rows = data.get(candidate)
        if isinstance(rows, list):
            return rows
    nested = data.get("data")
    if isinstance(nested, list):
        return nested
    keys = ", ".join(sorted(data.keys())) if isinstance(data, dict) else "n/a"
    msg = "no tabular rows in tool payload; use dojo_tools.tool_table(res) per schema_hint.tables; keys: " + keys
    if isinstance(hint, dict):
        row_fields = hint.get("row_fields")
        if isinstance(row_fields, list) and row_fields:
            msg += "; row_fields: " + ", ".join(str(f) for f in row_fields)
        example = hint.get("pandas_example")
        if example:
            msg += "; suggested: " + example
    raise KeyError(msg)


def _expand_bilingual(row, fields):
    out = dict(row)
    for field in fields or []:
        value = out.pop(field, None)
        if isinstance(value, dict):
            out[field + "_zh"] = value.get("zh") or ""
            out[field + "_en"] = value.get("en") or ""
        else:
            out[field + "_zh"] = ""
            out[field + "_en"] = ""
    return out


def _flatten_by_spec(data, spec):
    typ = str(spec.get("type") or "")
    if typ == "first_list":
        paths = spec.get("paths") or []
        for path in paths:
            rows = data.get(path) if isinstance(data, dict) else None
            if isinstance(rows, list) and rows:
                return [dict(row) if isinstance(row, dict) else {{"value": row}} for row in rows]
        if spec.get("record_fallback") and isinstance(data, dict) and data.get("ticker"):
            return [dict(data)]
        return []

    path = spec.get("path")
    subtree = data.get(path) if isinstance(data, dict) else None
    expand = spec.get("expand_bilingual") or []

    if typ == "list":
        if not isinstance(subtree, list):
            return []
        return [_expand_bilingual(dict(row), expand) if isinstance(row, dict) else {{"value": row}} for row in subtree]

    if typ == "dict_records":
        if not isinstance(subtree, dict):
            return []
        group_key = spec.get("group_key") or "key"
        rows = []
        for key, value in subtree.items():
            row = {{group_key: key}}
            if isinstance(value, dict):
                row.update(value)
            else:
                row["value"] = value
            rows.append(_expand_bilingual(row, expand))
        return rows

    if typ == "dict_list_records":
        if not isinstance(subtree, dict):
            return []
        group_key = spec.get("group_key") or "group"
        rows = []
        for key, value in subtree.items():
            if not isinstance(value, list):
                continue
            for item in value:
                row = {{group_key: key}}
                if isinstance(item, dict):
                    row.update(item)
                else:
                    row["value"] = item
                rows.append(_expand_bilingual(row, expand))
        return rows

    if typ == "dict_side_lists":
        if not isinstance(subtree, dict):
            return []
        group_key = spec.get("group_key") or "market"
        side_column = spec.get("side_column") or "side"
        sides = spec.get("sides") or ["gainers", "losers"]
        rank_by = spec.get("rank_by") or [group_key, side_column]
        rows = []
        counters = {{}}
        for group, payload in subtree.items():
            if not isinstance(payload, dict):
                continue
            for side in sides:
                for item in payload.get(side) or []:
                    if not isinstance(item, dict):
                        continue
                    row = {{group_key: group, side_column: side, **item}}
                    row = _expand_bilingual(row, expand)
                    bucket = tuple(row.get(k) for k in rank_by)
                    counters[bucket] = counters.get(bucket, 0) + 1
                    row["rank"] = counters[bucket]
                    rows.append(row)
        return rows

    raise KeyError("unsupported table spec type: " + typ)


def tool_table(res, table=None):
    """Materialize rows using schema_hint.tables[...] from load_tool_result / RPC responses."""
    data = tool_json(res)
    hint = res.get("schema_hint") if isinstance(res, dict) else None
    if not isinstance(hint, dict):
        raise KeyError("schema_hint is required; call via dojo_tools.load_tool_result(call_id)")
    tables = hint.get("tables") or {{}}
    name = table or hint.get("default_table")
    if not name or name not in tables:
        available = ", ".join(sorted(tables.keys())) or "(none)"
        raise KeyError(f"unknown table {{name!r}}; available: {{available}}")
    return _flatten_by_spec(data, tables[name])


'''
