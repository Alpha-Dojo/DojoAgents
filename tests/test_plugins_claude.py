import tempfile
import json
import os
from pathlib import Path
import pytest
from dojoagents.plugins.registry import DojoPluginRegistry, PluginManifest

def test_claude_manifest_scanning_and_variables():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdir = Path(tmpdir) / "test-claude-plugin"
        pdir.mkdir()
        
        # Write .claude-plugin/plugin.json
        claude_dir = pdir / ".claude-plugin"
        claude_dir.mkdir()
        
        manifest_data = {
            "name": "test-claude-plugin",
            "version": "1.2.3",
            "description": "Claude compatibility test",
            "hooks": {
                "PreToolUse": {
                    "command": "python ${CLAUDE_PLUGIN_ROOT}/hooks/pre_tool.py"
                }
            },
            "mcpServers": {
                "mock-server": {
                    "command": "${CLAUDE_PLUGIN_ROOT}/bin/mcp-server",
                    "args": []
                }
            }
        }
        
        with open(claude_dir / "plugin.json", "w") as f:
            json.dump(manifest_data, f)
            
        # Create bin/ and skills/ directory to trigger loading
        (pdir / "bin").mkdir()
        (pdir / "skills").mkdir()
        
        # Create agents directory and reviewer.md
        agents_dir = pdir / "agents"
        agents_dir.mkdir()
        reviewer_md = """---
name: reviewer
description: Review code changes
model: gemini-1.5-pro
maxTurns: 5
---
You are a code reviewer.
"""
        with open(agents_dir / "reviewer.md", "w") as f:
            f.write(reviewer_md)
        
        reg = DojoPluginRegistry()
        reg._scan_directory(Path(tmpdir), source="user")
        
        assert "test-claude-plugin" in reg._plugins
        
        # Verify agents directory loading
        assert len(reg._agent_configs) == 1
        agent_cfg = reg._agent_configs[0]
        assert agent_cfg["name"] == "reviewer"
        assert agent_cfg["description"] == "Review code changes"
        assert agent_cfg["model"] == "gemini-1.5-pro"
        assert agent_cfg["max_turns"] == 5
        assert agent_cfg["system_prompt"] == "You are a code reviewer."
        
        # Verify PATH injection
        expected_bin = str(pdir / "bin")
        path_list = os.environ.get("PATH", "").split(os.pathsep)
        assert expected_bin in path_list
        # Clean up path to avoid leaking into other tests
        if expected_bin in path_list:
            path_list.remove(expected_bin)
            os.environ["PATH"] = os.pathsep.join(path_list)
        
        # Verify skills directory loading
        assert Path(pdir / "skills") in reg._skill_dirs
        
        # Verify MCP server config loading & path resolution
        assert "mock-server" in reg._mcp_configs
        assert reg._mcp_configs["mock-server"]["command"] == str(pdir / "bin" / "mcp-server")
        
        # Verify hook parsing and translation
        pre_tool_hooks = reg._decl_hooks.get("pre_tool_call", [])
        assert len(pre_tool_hooks) == 1
        hook = pre_tool_hooks[0]
        assert hook["command"] == f"python {pdir}/hooks/pre_tool.py"
        assert hook["is_claude"] is True

def test_claude_stdin_hook_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdir = Path(tmpdir) / "test-claude-hook"
        pdir.mkdir()
        
        # Write plugin.json directly
        manifest_data = {
            "name": "test-claude-hook",
            "version": "1.0.0",
            "hooks": {
                "PreToolUse": {
                    "command": "python script.py"
                }
            }
        }
        with open(pdir / "plugin.json", "w") as f:
            json.dump(manifest_data, f)
            
        # Write script.py to read from stdin and write a decision to stdout
        script_content = """
import sys
import json

# Read event payload from stdin
input_data = sys.stdin.read()
payload = json.loads(input_data)

if payload.get("event") == "PreToolUse" and payload.get("tool_name") == "blocked_tool":
    print(json.dumps({"decision": "block", "reason": "blocked by hook stdin test"}))
else:
    print(json.dumps({"decision": "allow"}))
"""
        with open(pdir / "script.py", "w") as f:
            f.write(script_content)
            
        reg = DojoPluginRegistry()
        reg._scan_directory(Path(tmpdir), source="user")
        
        # Invoke pre_tool_call hook with allowed tool name
        results = reg.invoke_hook("pre_tool_call", tool_name="allowed_tool", args={}, session_id="s1")
        assert len(results) == 1
        assert results[0] == {"action": "allow", "message": ""}
        
        # Invoke pre_tool_call hook with blocked tool name
        results_blocked = reg.invoke_hook("pre_tool_call", tool_name="blocked_tool", args={}, session_id="s1")
        assert len(results_blocked) == 1
        assert results_blocked[0] == {"action": "block", "message": "blocked by hook stdin test"}

def test_conversational_plugin_management(monkeypatch):
    from unittest import mock
    with tempfile.TemporaryDirectory() as tmpdir:
        home_dir = Path(tmpdir)
        monkeypatch.setenv("HOME", str(home_dir))
        
        user_plugins_root = home_dir / ".dojo" / "plugins"
        user_plugins_root.mkdir(parents=True)
        
        # 1. Create a user plugin
        plugin_dir = user_plugins_root / "my-user-plugin"
        plugin_dir.mkdir()
        manifest_data = {
            "name": "my-user-plugin",
            "version": "2.0.0",
            "description": "User test plugin",
            "provides_tools": ["user_test_tool"],
            "mcpServers": {
                "dummy": {
                    "command": "echo",
                    "args": []
                }
            }
        }
        with open(plugin_dir / "plugin.json", "w") as f:
            json.dump(manifest_data, f)
            
        # 2. Setup the registry
        reg = DojoPluginRegistry()
        reg._scan_directory(user_plugins_root, source="user")
        
        assert "my-user-plugin" in reg._plugins
        assert "my-user-plugin" in reg._manifests
        manifest = reg._manifests["my-user-plugin"]
        assert manifest.version == "2.0.0"
        assert manifest.is_claude is True
        
        # 3. Test PluginListTool
        from dojoagents.tools.plugin_manage import PluginListTool, PluginDeleteTool
        list_tool = PluginListTool(reg)
        list_spec = list_tool.get_tool_spec()
        
        import asyncio
        loop = asyncio.new_event_loop()
        list_res = loop.run_until_complete(list_tool.handle_call({}))
        assert list_res["metadata"]["ok"] is True
        plugins_list = json.loads(list_res["content"])
        assert len(plugins_list) == 1
        assert plugins_list[0]["name"] == "my-user-plugin"
        assert plugins_list[0]["is_claude"] is True
        
        # 4. Test PluginDeleteTool safety checks: try to delete a non-existent plugin
        delete_tool = PluginDeleteTool(reg)
        delete_res = loop.run_until_complete(delete_tool.handle_call({"name": "non-existent"}))
        assert delete_res["metadata"]["ok"] is False
        assert "not found" in delete_res["content"]
        
        # 5. Test PluginDeleteTool safety checks: try to delete built-in plugin
        reg._manifests["mock-builtin"] = PluginManifest(
            name="mock-builtin",
            version="1.0.0",
            source="built_in",
            path=str(home_dir / "mock-builtin")
        )
        delete_res = loop.run_until_complete(delete_tool.handle_call({"name": "mock-builtin"}))
        assert delete_res["metadata"]["ok"] is False
        assert "Cannot delete built-in" in delete_res["content"]
        
        # 6. Test PluginDeleteTool safety checks: try to delete with path traversal
        reg._manifests["malicious-plugin"] = PluginManifest(
            name="malicious-plugin",
            version="1.0.0",
            source="user",
            path=str(home_dir / "outside-dir")
        )
        delete_res = loop.run_until_complete(delete_tool.handle_call({"name": "malicious-plugin"}))
        assert delete_res["metadata"]["ok"] is False
        assert "Security Error" in delete_res["content"]
        
        # 7. Test PluginDeleteTool: successful deletion
        delete_res = loop.run_until_complete(delete_tool.handle_call({"name": "my-user-plugin"}))
        assert delete_res["metadata"]["ok"] is True
        assert "deleted successfully" in delete_res["content"]
        
        # Verify it was deleted from registry
        assert "my-user-plugin" not in reg._plugins
        assert "my-user-plugin" not in reg._manifests
        # Verify directory is gone
        assert not plugin_dir.exists()
        
        # Re-create for Gateway command routing test
        plugin_dir.mkdir()
        with open(plugin_dir / "plugin.json", "w") as f:
            json.dump(manifest_data, f)
        reg.discover_and_load(force=True)
        
        # Mock get_plugin_registry to return our registry instance
        with mock.patch("dojoagents.plugins.get_plugin_registry", return_value=reg):
            from dojoagents.gateway.runner import GatewayRunner
            from dojoagents.gateway.adapters.base import GatewayEvent
            
            mock_runtime = mock.MagicMock()
            mock_runtime.agent.skill_manager.list_skills.return_value = []
            
            class MockAdapter:
                def __init__(self):
                    self.sent = []
                async def send(self, target, msg, thread_id=None):
                    self.sent.append((target, msg, thread_id))
                    return mock.MagicMock()
            
            runner = GatewayRunner(
                runtime=mock_runtime,
                gateway_config={
                    "session_store": str(home_dir / "state.db"),
                    "pid_file": str(home_dir / "gateway.pid")
                }
            )
            adapter = MockAdapter()
            
            # test /plugins list
            event_list = GatewayEvent(
                platform="test",
                text="/plugins list",
                target="channel1",
                user_id="user1",
                raw={}
            )
            res = loop.run_until_complete(runner._handle_command(adapter, event_list))
            assert res is not None
            assert res["command"] == "plugins-list"
            assert len(adapter.sent) == 1
            assert "my-user-plugin" in adapter.sent[0][1]
            
            # test /plugins delete
            adapter.sent.clear()
            event_delete = GatewayEvent(
                platform="test",
                text="/plugins delete my-user-plugin",
                target="channel1",
                user_id="user1",
                raw={}
            )
            res = loop.run_until_complete(runner._handle_command(adapter, event_delete))
            assert res is not None
            assert res["command"] == "plugins-delete"
            assert len(adapter.sent) == 1
            assert "deleted successfully" in adapter.sent[0][1]
            assert "my-user-plugin" not in reg._manifests
