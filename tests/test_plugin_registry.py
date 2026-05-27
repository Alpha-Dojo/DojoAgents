import tempfile
import json
from pathlib import Path
import yaml
from dojoagents.plugins.registry import DojoPluginRegistry, DojoPluginContext, PluginManifest

def test_registration_and_hooks():
    reg = DojoPluginRegistry()
    manifest = PluginManifest(name="test_plugin", path="/tmp")
    ctx = DojoPluginContext(manifest, reg)
    
    # Test hook registration
    calls = []
    ctx.register_hook("pre_llm_call", lambda session_id, user_message: f"hook called for {user_message}")
    
    results = reg.invoke_hook("pre_llm_call", session_id="s1", user_message="hello")
    assert len(results) == 1
    assert results[0] == "hook called for hello"

def test_load_plugin_from_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdir = Path(tmpdir) / "test_plugin"
        pdir.mkdir()
        
        # Write plugin.yaml
        with open(pdir / "plugin.yaml", "w") as f:
            yaml.dump({"name": "test_plugin", "version": "1.0.0", "description": "Test"}, f)
            
        # Write __init__.py
        with open(pdir / "__init__.py", "w") as f:
            f.write('''
def register(ctx):
    ctx.register_hook("on_session_end", lambda session_id, completed: "session ended")
''')
            
        reg = DojoPluginRegistry()
        reg._scan_directory(Path(tmpdir), source="user")
        assert "test_plugin" in reg._plugins
        results = reg.invoke_hook("on_session_end", session_id="s1", completed=True)
        assert results == ["session ended"]

def test_declarative_plugin_yaml_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdir = Path(tmpdir) / "test_decl_plugin"
        pdir.mkdir()
        
        # Write plugin.yaml mapping pre_llm_call to command
        with open(pdir / "plugin.yaml", "w") as f:
            yaml.dump({
                "name": "test_decl_plugin",
                "version": "1.0.0",
                "hooks": {
                    "pre_llm_call": {
                        "command": "echo '{\"additionalContext\": \"shell-injected\"}'"
                    }
                }
            }, f)
            
        reg = DojoPluginRegistry()
        reg._scan_directory(Path(tmpdir), source="user")
        assert "test_decl_plugin" in reg._plugins
        results = reg.invoke_hook("pre_llm_call", session_id="s1", user_message="hello")
        assert results == ["shell-injected"]

def test_declarative_plugin_hooks_json_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdir = Path(tmpdir) / "test_hooks_json_plugin"
        pdir.mkdir()
        
        # Write plugin.yaml metadata
        with open(pdir / "plugin.yaml", "w") as f:
            yaml.dump({
                "name": "test_hooks_json_plugin",
                "version": "1.0.0"
            }, f)
            
        # Write hooks.json
        with open(pdir / "hooks.json", "w") as f:
            json.dump({
                "hooks": {
                    "pre_tool_call": {
                        "command": "echo '{\"action\": \"block\", \"message\": \"blocked-by-json\"}'"
                    }
                }
            }, f)
            
        reg = DojoPluginRegistry()
        reg._scan_directory(Path(tmpdir), source="user")
        results = reg.invoke_hook("pre_tool_call", tool_name="some_tool", args={})
        assert len(results) == 1
        assert results[0].get("action") == "block"
        assert results[0].get("message") == "blocked-by-json"
