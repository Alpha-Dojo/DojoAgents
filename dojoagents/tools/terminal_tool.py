import json
import re
from dojoagents.tools.registry import ToolSpec
from dojoagents.tools.environments.local import LocalEnvironment
from dojoagents.tools.sandbox import SandboxPolicy

ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(text: str) -> str:
    if not text:
        return ""
    return ANSI_ESCAPE_RE.sub("", text)

def truncate_output(text: str, limit: int = 30000) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    head_len = int(limit * 0.4)
    tail_len = limit - head_len
    omitted = len(text) - head_len - tail_len
    notice = f"\n\n... [OUTPUT TRUNCATED - {omitted} chars omitted] ...\n\n"
    return text[:head_len] + notice + text[-tail_len:]

async def handle_terminal(args: dict, policy: SandboxPolicy) -> dict:
    command = args.get("command")
    background = args.get("background", False)
    notify_on_complete = args.get("notify_on_complete", False)
    
    if background:
        from dojoagents.tools.process_registry import process_registry, active_session_id
        session = await process_registry.spawn(command)
        session.session_key = active_session_id.get()
        session.notify_on_complete = notify_on_complete
        return {
            "content": f"Background process started with session ID: {session.id}",
            "metadata": {
                "session_id": session.id,
                "exit_code": 0,
                "background": True
            }
        }

    env = LocalEnvironment(policy=policy)
    raw_res = await env.execute(command)
    
    # 获取输出并进行清理
    output = raw_res.get("output", "")
    output = strip_ansi(output)
    output = truncate_output(output)
    
    return {
        "content": output,
        "metadata": {"exit_code": raw_res.get("exit_code", 0)}
    }

def get_terminal_spec(policy: SandboxPolicy) -> ToolSpec:
    return ToolSpec(
        name="terminal",
        description=(
            "Execute shell commands on a Linux environment. "
            "Do NOT use for writing JSON/JSONL deliverables — use write_session_file instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to execute"},
                "background": {"type": "boolean", "description": "Whether to run command in background", "default": False},
                "notify_on_complete": {"type": "boolean", "description": "Whether to notify the user/agent when background process completes", "default": False}
            },
            "required": ["command"]
        },
        handler=lambda args: handle_terminal(args, policy)
    )
