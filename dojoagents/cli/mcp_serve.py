from mcp.server.fastmcp import FastMCP
from dojoagents.gateway.state import GatewaySessionStore

mcp = FastMCP("DojoAgents Outbound MCP Server")

@mcp.tool()
def list_chat_sessions() -> str:
    """List all active and stored DojoAgents chat sessions."""
    store = GatewaySessionStore("~/.dojo/gateway/state.db")
    sessions = store.sessions
    if not sessions:
        return "No chat sessions found."
    lines = []
    for key, s in sessions.items():
        lines.append(f"- Key: {s.key} | Platform: {s.platform} | User: {s.user_id} | Status: {s.status}")
    return "\n".join(lines)

@mcp.tool()
def get_chat_history(session_key: str) -> str:
    """Retrieve chat transcript history for a specific session key."""
    store = GatewaySessionStore("~/.dojo/gateway/state.db")
    if session_key not in store.sessions:
        return f"Session key '{session_key}' not found."
    history = store.get_history(session_key, limit=50)
    if not history:
        return f"No history found for session '{session_key}'."
    lines = []
    for turn in history:
        role = turn.get("role", "unknown").upper()
        content = turn.get("content", "")
        lines.append(f"[{role}]: {content}")
    return "\n\n".join(lines)

def run_server():
    """Start the stdio FastMCP server."""
    mcp.run()
