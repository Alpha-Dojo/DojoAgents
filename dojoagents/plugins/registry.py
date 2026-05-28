from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

LOGGER = logging.getLogger("dojoagents.plugins")

# 定义支持的生命周期钩子
VALID_HOOKS = {
    "on_session_start",
    "pre_llm_call",
    "pre_api_request",
    "post_api_request",
    "pre_tool_call",
    "post_tool_call",
    "transform_tool_result",
    "transform_llm_output",
    "post_llm_call",
    "on_session_end",
}

CLAUDE_TO_DOJO_HOOKS = {
    "SessionStart": "on_session_start",
    "UserPromptSubmit": "pre_llm_call",
    "PreToolUse": "pre_tool_call",
    "PostToolUse": "post_tool_call",
    "SessionEnd": "on_session_end"
}

@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    provides_tools: List[str] = field(default_factory=list)
    provides_hooks: List[str] = field(default_factory=list)
    path: Optional[str] = None
    source: str = "user"  # "built_in" 或 "user"
    is_claude: bool = False

class DojoPluginContext:
    """提供给插件的注册接口上下文 Facade"""
    def __init__(self, manifest: PluginManifest, registry: DojoPluginRegistry):
        self.manifest = manifest
        self._registry = registry

    def register_hook(self, hook_name: str, callback: Callable) -> None:
        if hook_name not in VALID_HOOKS:
            LOGGER.warning(f"Plugin '{self.manifest.name}' registered unknown hook '{hook_name}'")
        self._registry._hooks.setdefault(hook_name, []).append(callback)
        LOGGER.info(f"Registered hook '{hook_name}' from plugin '{self.manifest.name}'")

    def register_tool(self, name: str, schema: dict, handler: Callable) -> None:
        from dojoagents.tools.registry import ToolSpec
        description = schema.get("description", "")
        parameters = schema.get("parameters", {"type": "object", "properties": {}})
        spec = ToolSpec(name=name, description=description, parameters=parameters, handler=handler)
        self._registry._tools.append(spec)
        LOGGER.info(f"Registered tool '{name}' from plugin '{self.manifest.name}'")


class DojoPluginRegistry:
    """独立的插件注册表与管理器"""
    def __init__(self) -> None:
        self._plugins: Dict[str, Any] = {}
        self._hooks: Dict[str, List[Callable]] = {}
        self._decl_hooks: Dict[str, List[Dict[str, Any]]] = {}  # 声明式钩子字典
        self._tools: List[Any] = []  # 插件注册的自定义工具列表
        self._skill_dirs: List[Path] = []
        self._mcp_configs: Dict[str, Dict[str, Any]] = {}
        self._agent_configs: List[Dict[str, Any]] = []
        self._manifests: Dict[str, PluginManifest] = {}
        self._discovered = False

    def _resolve_manifest_paths(self, data: Any, root_path: str) -> Any:
        if isinstance(data, str):
            resolved = data.replace("${CLAUDE_PLUGIN_ROOT}", root_path).replace("${DOJO_PLUGIN_ROOT}", root_path)
            if resolved != data:
                LOGGER.debug(f"Resolved path template: {data} -> {resolved} using root {root_path}")
            return resolved
        elif isinstance(data, list):
            return [self._resolve_manifest_paths(x, root_path) for x in data]
        elif isinstance(data, dict):
            return {k: self._resolve_manifest_paths(v, root_path) for k, v in data.items()}
        return data

    def discover_and_load(self, force: bool = False) -> None:
        if self._discovered and not force:
            return

        if force:
            self._plugins.clear()
            self._hooks.clear()
            self._decl_hooks.clear()
            self._tools.clear()
            self._skill_dirs.clear()
            self._mcp_configs.clear()
            self._agent_configs.clear()
            self._manifests.clear()

        # 1. 扫描并加载内置插件 (dojoagents/plugins/built_in)
        built_in_dir = Path(__file__).resolve().parent / "built_in"
        self._scan_directory(built_in_dir, source="built_in")

        # 2. 扫描并加载用户自定义插件 (~/.dojo/plugins)
        user_dir = Path("~/.dojo/plugins").expanduser()
        self._scan_directory(user_dir, source="user")

        self._discovered = True

    def _scan_directory(self, path: Path, source: str) -> None:
        if not path.exists() or not path.is_dir():
            if source == "user":
                path.mkdir(parents=True, exist_ok=True)
            return

        LOGGER.debug(f"Scanning directory: {path} (source: {source})")
        LOGGER.info(f"Scanning {source} plugins in {path}")
        for child in path.iterdir():
            if not child.is_dir():
                continue
            
            yaml_file = child / "plugin.yaml"
            claude_plugin_json = child / ".claude-plugin" / "plugin.json"
            direct_plugin_json = child / "plugin.json"
            
            meta = None
            is_claude = False
            
            if yaml_file.exists():
                LOGGER.debug(f"Found Dojo native manifest at {yaml_file} for directory {child.name}")
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        meta = yaml.safe_load(f) or {}
                except Exception as e:
                    LOGGER.error(f"Failed to load plugin.yaml from {child}: {e}")
            elif claude_plugin_json.exists():
                LOGGER.debug(f"Found Claude compatibility manifest at {claude_plugin_json} for directory {child.name}")
                try:
                    with open(claude_plugin_json, "r", encoding="utf-8") as f:
                        meta = json.load(f) or {}
                        is_claude = True
                except Exception as e:
                    LOGGER.error(f"Failed to load .claude-plugin/plugin.json from {child}: {e}")
            elif direct_plugin_json.exists():
                LOGGER.debug(f"Found Claude compatibility manifest at {direct_plugin_json} for directory {child.name}")
                try:
                    with open(direct_plugin_json, "r", encoding="utf-8") as f:
                        meta = json.load(f) or {}
                        is_claude = True
                except Exception as e:
                    LOGGER.error(f"Failed to load plugin.json from {child}: {e}")
            
            if meta is None:
                continue
            
            try:
                manifest = PluginManifest(
                    name=meta.get("name", child.name),
                    version=meta.get("version", "0.1.0"),
                    description=meta.get("description", ""),
                    provides_tools=meta.get("provides_tools", []),
                    provides_hooks=meta.get("provides_hooks", []),
                    path=str(child),
                    source=source,
                    is_claude=is_claude
                )

                self._load_plugin(manifest)
            except Exception as e:
                LOGGER.error(f"Failed to load plugin from {child}: {e}", exc_info=True)

    def _load_plugin(self, manifest: PluginManifest) -> None:
        init_file = Path(manifest.path) / "__init__.py"
        yaml_file = Path(manifest.path) / "plugin.yaml"
        hooks_json_file = Path(manifest.path) / "hooks.json"
        claude_plugin_json = Path(manifest.path) / ".claude-plugin" / "plugin.json"
        direct_plugin_json = Path(manifest.path) / "plugin.json"
        claude_hooks_json = Path(manifest.path) / "hooks" / "hooks.json"

        # 1. 从 plugin.yaml, .claude-plugin/plugin.json 或 plugin.json 中解析声明式 meta 与 is_claude
        meta = {}
        is_claude = False

        if yaml_file.exists():
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    meta = yaml.safe_load(f) or {}
            except Exception as e:
                LOGGER.error(f"Failed to load plugin.yaml metadata in {manifest.name}: {e}")
        elif claude_plugin_json.exists():
            try:
                with open(claude_plugin_json, "r", encoding="utf-8") as f:
                    meta = json.load(f) or {}
                    is_claude = True
            except Exception as e:
                LOGGER.error(f"Failed to load .claude-plugin/plugin.json metadata in {manifest.name}: {e}")
        elif direct_plugin_json.exists():
            try:
                with open(direct_plugin_json, "r", encoding="utf-8") as f:
                    meta = json.load(f) or {}
                    is_claude = True
            except Exception as e:
                LOGGER.error(f"Failed to load plugin.json metadata in {manifest.name}: {e}")

        manifest.is_claude = is_claude
        self._manifests[manifest.name] = manifest

        # 2. 从 hooks.json 或 hooks/hooks.json 中解析 hooks
        if hooks_json_file.exists():
            try:
                with open(hooks_json_file, "r", encoding="utf-8") as f:
                    hooks_data = json.load(f) or {}
                    meta["hooks"] = hooks_data.get("hooks", {})
            except Exception as e:
                LOGGER.error(f"Failed to load hooks.json in {manifest.name}: {e}")
        elif claude_hooks_json.exists():
            try:
                with open(claude_hooks_json, "r", encoding="utf-8") as f:
                    hooks_data = json.load(f) or {}
                    if "hooks" in hooks_data:
                        meta["hooks"] = hooks_data["hooks"]
                    else:
                        meta["hooks"] = hooks_data
            except Exception as e:
                LOGGER.error(f"Failed to load hooks/hooks.json in {manifest.name}: {e}")

        # 3. 递归解析路径变量
        meta = self._resolve_manifest_paths(meta, manifest.path)

        # 4. 加载 MCP configs
        mcp_configs = {}
        if "mcpServers" in meta and isinstance(meta["mcpServers"], dict):
            mcp_configs.update(meta["mcpServers"])
        
        mcp_json_file = Path(manifest.path) / ".mcp.json"
        if mcp_json_file.exists():
            try:
                with open(mcp_json_file, "r", encoding="utf-8") as f:
                    mcp_data = json.load(f) or {}
                    mcp_data = self._resolve_manifest_paths(mcp_data, manifest.path)
                    if "mcpServers" in mcp_data and isinstance(mcp_data["mcpServers"], dict):
                        mcp_configs.update(mcp_data["mcpServers"])
                    elif isinstance(mcp_data, dict):
                        mcp_configs.update(mcp_data)
            except Exception as e:
                LOGGER.error(f"Failed to load .mcp.json in {manifest.name}: {e}")

        if mcp_configs:
            self._mcp_configs.update(mcp_configs)
            LOGGER.info(f"Loaded {len(mcp_configs)} MCP server configs from plugin '{manifest.name}'")

        # 5. 保存声明式构件/钩子至注册表
        has_decl_hooks = False
        if "hooks" in meta and isinstance(meta["hooks"], dict):
            for raw_hook_name, hook_cfg in meta["hooks"].items():
                hook_name = CLAUDE_TO_DOJO_HOOKS.get(raw_hook_name, raw_hook_name)
                cfg_list = hook_cfg if isinstance(hook_cfg, list) else [hook_cfg]
                for item in cfg_list:
                    if isinstance(item, dict) and "command" in item:
                        LOGGER.debug(f"Registered declarative hook '{hook_name}' for plugin '{manifest.name}' calling command '{item['command']}'")
                        self._decl_hooks.setdefault(hook_name, []).append({
                            "plugin_name": manifest.name,
                            "plugin_path": manifest.path,
                            "command": item["command"],
                            "matcher": item.get("matcher"),
                            "async": item.get("async", False),
                            "is_claude": is_claude or (raw_hook_name in CLAUDE_TO_DOJO_HOOKS)
                        })
                        has_decl_hooks = True
                    elif isinstance(item, str):
                        LOGGER.debug(f"Registered declarative hook '{hook_name}' for plugin '{manifest.name}' calling command '{item}'")
                        self._decl_hooks.setdefault(hook_name, []).append({
                            "plugin_name": manifest.name,
                            "plugin_path": manifest.path,
                            "command": item,
                            "matcher": None,
                            "async": False,
                            "is_claude": is_claude or (raw_hook_name in CLAUDE_TO_DOJO_HOOKS)
                        })
                        has_decl_hooks = True

        # 6. 加载自定义 skills 文件夹
        skills_dir = Path(manifest.path) / "skills"
        if skills_dir.exists() and skills_dir.is_dir():
            self._skill_dirs.append(skills_dir)
            LOGGER.info(f"Loaded skills directory from plugin '{manifest.name}': {skills_dir}")

        # 7. PATH 环境变量注入
        bin_dir = Path(manifest.path) / "bin"
        if bin_dir.exists() and bin_dir.is_dir():
            bin_path_str = str(bin_dir)
            current_path = os.environ.get("PATH", "")
            if bin_path_str not in current_path.split(os.pathsep):
                LOGGER.debug(f"Injecting path '{bin_dir}' to os.environ['PATH'] for plugin '{manifest.name}'")
                os.environ["PATH"] = bin_path_str + os.pathsep + current_path
                LOGGER.info(f"Prepended '{bin_path_str}' to system PATH from plugin '{manifest.name}'")

        # 7.5. 加载自定义 agents/ 文件夹下 md 配置
        has_agent_configs = False
        agents_dir = Path(manifest.path) / "agents"
        if agents_dir.exists() and agents_dir.is_dir():
            for agent_file in agents_dir.glob("*.md"):
                try:
                    with open(agent_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    import re
                    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
                    if match:
                        fm_text, body = match.groups()
                        fm = yaml.safe_load(fm_text) or {}
                    else:
                        fm = {}
                        body = content
                    
                    agent_name = fm.get("name", agent_file.stem)
                    LOGGER.debug(f"Parsed agent configuration '{agent_name}' for plugin '{manifest.name}' from {agent_file}")
                    self._agent_configs.append({
                        "name": agent_name,
                        "description": fm.get("description", ""),
                        "system_prompt": fm.get("systemPrompt", fm.get("system_prompt", body.strip())),
                        "model": fm.get("model"),
                        "effort": fm.get("effort"),
                        "max_turns": fm.get("maxTurns", fm.get("max_turns")),
                        "disallowed_tools": fm.get("disallowedTools", fm.get("disallowed_tools", []))
                    })
                    has_agent_configs = True
                    LOGGER.info(f"Loaded agent config '{agent_name}' from plugin '{manifest.name}'")
                except Exception as e:
                    LOGGER.error(f"Failed to load agent config from {agent_file}: {e}")

        # 8. 如果 __init__.py 存在，加载命令式 Python 插件
        has_py_module = False
        if init_file.exists():
            module_name = f"dojo_plugins.{manifest.source}.{manifest.name}"
            LOGGER.debug(f"Loading dynamic Python plugin module '{module_name}' from {init_file}")
            spec = importlib.util.spec_from_file_location(module_name, init_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create spec for {init_file}")

            LOGGER.debug(f"Executing Python module loader for plugin '{manifest.name}'")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            register_fn = getattr(module, "register", None)
            if register_fn:
                ctx = DojoPluginContext(manifest, self)
                register_fn(ctx)
                self._plugins[manifest.name] = module
                has_py_module = True
                LOGGER.info(f"Successfully registered Python plugin module '{manifest.name}' ({manifest.source})")

        # 9. 如果是纯声明式插件，将其存入注册列表
        if (has_decl_hooks or mcp_configs or skills_dir.exists() or has_agent_configs) and not has_py_module:
            self._plugins[manifest.name] = manifest
            LOGGER.info(f"Successfully registered declarative plugin '{manifest.name}' ({manifest.source})")

    def _run_shell_hook(self, hook: Dict[str, Any], hook_name: str, **kwargs: Any) -> Any:
        command = hook["command"]
        plugin_path = hook["plugin_path"]
        
        env = os.environ.copy()
        env["DOJO_PLUGIN_ROOT"] = plugin_path
        env["DOJO_HOOK_EVENT"] = hook_name
        
        if "session_id" in kwargs:
            env["DOJO_SESSION_ID"] = str(kwargs["session_id"])
            env["SESSION_ID"] = str(kwargs["session_id"])
        if "user_message" in kwargs:
            env["DOJO_USER_MESSAGE"] = str(kwargs["user_message"])
            env["USER_MESSAGE"] = str(kwargs["user_message"])
        if "tool_name" in kwargs:
            env["DOJO_TOOL_NAME"] = str(kwargs["tool_name"])
            env["TOOL_NAME"] = str(kwargs["tool_name"])
        if "args" in kwargs:
            env["DOJO_TOOL_ARGS"] = json.dumps(kwargs["args"], ensure_ascii=False)
        if "tool_call_id" in kwargs:
            env["DOJO_TOOL_CALL_ID"] = str(kwargs["tool_call_id"])
        if "result" in kwargs:
            env["DOJO_TOOL_RESULT"] = str(kwargs["result"])
        if "duration_ms" in kwargs:
            env["DOJO_DURATION_MS"] = str(kwargs["duration_ms"])
            
        input_data = None
        if hook.get("is_claude"):
            CLAUDE_HOOKS_MAP = {v: k for k, v in CLAUDE_TO_DOJO_HOOKS.items()}
            claude_event_name = CLAUDE_HOOKS_MAP.get(hook_name, hook_name)
            payload = {
                "event": claude_event_name,
                "session_id": str(kwargs.get("session_id", "")),
                "cwd": str(kwargs.get("cwd", os.getcwd())),
            }
            if "user_message" in kwargs:
                payload["user_message"] = str(kwargs["user_message"])
            if "tool_name" in kwargs:
                payload["tool_name"] = str(kwargs["tool_name"])
            if "args" in kwargs:
                payload["tool_input"] = kwargs["args"]
            if "result" in kwargs:
                payload["tool_output"] = str(kwargs["result"])
            input_data = json.dumps(payload, ensure_ascii=False)

        LOGGER.debug(f"Executing hook command: '{command}' in cwd: '{plugin_path}' with Claude-style stdin: {input_data}")
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=plugin_path,
                capture_output=True,
                text=True,
                input=input_data,
                env=env,
                timeout=5.0
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning(f"Hook command '{command}' in '{hook['plugin_name']}' timed out.")
            return None
            
        if res.returncode != 0:
            LOGGER.error(f"Hook command failed with exit {res.returncode}. stderr: {res.stderr}")
            return None

        output = res.stdout.strip()
        LOGGER.debug(f"Hook command '{command}' output stdout: '{output}' (exit code: {res.returncode})")
        if not output:
            return None
            
        try:
            data = json.loads(output)
            LOGGER.debug(f"Successfully decoded hook JSON decision output: {data}")
            if isinstance(data, dict):
                if "additionalContext" in data:
                    return data["additionalContext"]
                if "additional_context" in data:
                    return data["additional_context"]
                if "action" in data:
                    return data
                if "decision" in data:
                    return {"action": data["decision"], "message": data.get("reason", "")}
                if "result" in data:
                    return data["result"]
            return data
        except json.JSONDecodeError:
            LOGGER.error(f"Failed to decode hook output as JSON, falling back to raw string: {output}")
            return output

    def invoke_hook(self, hook_name: str, **kwargs: Any) -> List[Any]:
        results = []
        
        # 1. 执行命令式 Python 回调
        callbacks = self._hooks.get(hook_name, [])
        for cb in callbacks:
            try:
                ret = cb(**kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as e:
                LOGGER.error(f"Error in hook '{hook_name}' execution: {e}", exc_info=True)

        # 2. 执行声明式 Shell 钩子
        decl_hooks = self._decl_hooks.get(hook_name, [])
        for hook in decl_hooks:
            matcher = hook["matcher"]
            if matcher and "tool_name" in kwargs:
                import re
                LOGGER.debug(f"Checking matcher regex '{matcher}' against tool name '{kwargs.get('tool_name')}' for plugin '{hook['plugin_name']}'")
                try:
                    if not re.search(matcher, kwargs["tool_name"]):
                        continue
                except Exception as re_err:
                    LOGGER.error(f"Invalid matcher regex '{matcher}' in plugin '{hook['plugin_name']}': {re_err}")
                    continue
            
            try:
                ret = self._run_shell_hook(hook, hook_name, **kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as e:
                LOGGER.error(f"Error in declarative hook '{hook_name}' in plugin '{hook['plugin_name']}': {e}", exc_info=True)
                
        return results
