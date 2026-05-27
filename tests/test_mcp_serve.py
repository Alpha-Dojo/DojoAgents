from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from dojoagents.cli.main import build_parser
from dojoagents.cli.mcp_serve import mcp, list_chat_sessions, get_chat_history

def test_mcp_serve_cli_parser():
    parser = build_parser()
    args = parser.parse_args(["mcp", "serve"])
    assert args.command == "mcp"
    assert args.mcp_command == "serve"

def test_fastmcp_tools_registration():
    # Verify that the two tools are registered on the FastMCP instance
    tool_names = list(mcp._tool_manager._tools.keys())
    assert "list_chat_sessions" in tool_names
    assert "get_chat_history" in tool_names

def test_list_chat_sessions_empty():
    with patch("dojoagents.cli.mcp_serve.GatewaySessionStore") as mock_store_cls:
        mock_store = MagicMock()
        mock_store.sessions = {}
        mock_store_cls.return_value = mock_store
        
        res = list_chat_sessions()
        assert res == "No chat sessions found."

def test_list_chat_sessions_with_items():
    with patch("dojoagents.cli.mcp_serve.GatewaySessionStore") as mock_store_cls:
        mock_store = MagicMock()
        mock_s1 = MagicMock()
        mock_s1.key = "session_1"
        mock_s1.platform = "wechat"
        mock_s1.user_id = "user_123"
        mock_s1.status = "idle"
        mock_store.sessions = {"session_1": mock_s1}
        mock_store_cls.return_value = mock_store
        
        res = list_chat_sessions()
        assert "session_1" in res
        assert "wechat" in res

def test_get_chat_history():
    with patch("dojoagents.cli.mcp_serve.GatewaySessionStore") as mock_store_cls:
        mock_store = MagicMock()
        mock_s1 = MagicMock()
        mock_store.sessions = {"session_1": mock_s1}
        mock_store.get_history.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"}
        ]
        mock_store_cls.return_value = mock_store
        
        res = get_chat_history("session_1")
        assert "[USER]: hello" in res
        assert "[ASSISTANT]: hi" in res
