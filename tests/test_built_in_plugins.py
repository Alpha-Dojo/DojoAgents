from dojoagents.plugins import get_plugin_registry


def _clear_plugin_registry_state() -> None:
    reg = get_plugin_registry()
    reg._hooks.clear()
    reg._decl_hooks.clear()
    reg._tools.clear()
    reg._plugins.clear()
    reg._manifests.clear()


def test_built_in_example_plugin_loads():
    _clear_plugin_registry_state()
    reg = get_plugin_registry()
    reg.discover_and_load(force=True)
    assert "example_plugin" in reg._plugins

    # Test Hook
    res = reg.invoke_hook("pre_llm_call", session_id="s1", user_message="hello")
    assert any("提示：插件已挂载并开始监听本轮对话。" in r for r in res)
    assert reg.invoke_hook("transform_llm_output", response_text="hello", session_id="s1") == []


def test_built_in_project_guardian_blocks_malicious_commands():
    _clear_plugin_registry_state()
    reg = get_plugin_registry()
    reg.discover_and_load(force=True)
    assert "project_guardian" in reg._plugins

    # Test malicious command blocking
    res_malicious = reg.invoke_hook("pre_tool_call", tool_name="bash", args={"command": "rm -rf /data"}, session_id="s1", tool_call_id="call_malicious")
    # Check that at least one hook returned a block action
    assert any(isinstance(r, dict) and r.get("action") == "block" for r in res_malicious)

    # Test safe command allowing
    res_safe = reg.invoke_hook("pre_tool_call", tool_name="bash", args={"command": "echo 'hello'"}, session_id="s1", tool_call_id="call_safe")
    # Check that the hook returned allow
    assert any(isinstance(r, dict) and r.get("action") == "allow" for r in res_safe)
