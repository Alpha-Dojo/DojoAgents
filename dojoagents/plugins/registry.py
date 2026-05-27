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

@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    provides_tools: List[str] = field(default_factory=list)
    provides_hooks: List[str] = field(default_factory=list)
    path: Optional[str] = None
    source: str = "user"  # "built_in" 或 "user"

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
        self._discovered = False

    def discover_and_load(self, force: bool = False) -> None:
        if self._discovered and not force:
            return

        if force:
            self._plugins.clear()
            self._hooks.clear()
            self._decl_hooks.clear()
            self._tools.clear()

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

        LOGGER.info(f"Scanning {source} plugins in {path}")
        for child in path.iterdir():
            if not child.is_dir():
                continue
            
            yaml_file = child / "plugin.yaml"
            if not yaml_file.exists():
                continue
            
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    meta = yaml.safe_load(f) or {}
                
                manifest = PluginManifest(
                    name=meta.get("name", child.name),
                    version=meta.get("version", "0.1.0"),
                    description=meta.get("description", ""),
                    provides_tools=meta.get("provides_tools", []),
                    provides_hooks=meta.get("provides_hooks", []),
                    path=str(child),
                    source=source
                )

                self._load_plugin(manifest)
            except Exception as e:
                LOGGER.error(f"Failed to load plugin from {child}: {e}", exc_info=True)

    def _load_plugin(self, manifest: PluginManifest) -> None:
        init_file = Path(manifest.path) / "__init__.py"
        yaml_file = Path(manifest.path) / "plugin.yaml"
        hooks_json_file = Path(manifest.path) / "hooks.json"

        # 1. 从 plugin.yaml 中解析声明式 hooks 
        meta = {}
        if yaml_file.exists():
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    meta = yaml.safe_load(f) or {}
            except Exception as e:
                LOGGER.error(f"Failed to load plugin.yaml metadata in {manifest.name}: {e}")

        # 2. 从 hooks.json (兼容 superpowers 规范) 中解析 hooks
        if hooks_json_file.exists():
            try:
                with open(hooks_json_file, "r", encoding="utf-8") as f:
                    hooks_data = json.load(f) or {}
                    meta["hooks"] = hooks_data.get("hooks", {})
            except Exception as e:
                LOGGER.error(f"Failed to load hooks.json in {manifest.name}: {e}")

        # 3. 保存声明式钩子至注册表
        has_decl_hooks = False
        if "hooks" in meta and isinstance(meta["hooks"], dict):
            for hook_name, hook_cfg in meta["hooks"].items():
                cfg_list = hook_cfg if isinstance(hook_cfg, list) else [hook_cfg]
                for item in cfg_list:
                    if isinstance(item, dict) and "command" in item:
                        self._decl_hooks.setdefault(hook_name, []).append({
                            "plugin_name": manifest.name,
                            "plugin_path": manifest.path,
                            "command": item["command"],
                            "matcher": item.get("matcher"),
                            "async": item.get("async", False)
                        })
                        has_decl_hooks = True
                    elif isinstance(item, str):
                        self._decl_hooks.setdefault(hook_name, []).append({
                            "plugin_name": manifest.name,
                            "plugin_path": manifest.path,
                            "command": item,
                            "matcher": None,
                            "async": False
                        })
                        has_decl_hooks = True

        # 4. 如果 __init__.py 存在，加载命令式 Python 插件
        has_py_module = False
        if init_file.exists():
            module_name = f"dojo_plugins.{manifest.source}.{manifest.name}"
            spec = importlib.util.spec_from_file_location(module_name, init_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create spec for {init_file}")

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

        # 5. 如果是纯声明式插件，将其存入注册列表
        if has_decl_hooks and not has_py_module:
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
            
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=plugin_path,
                capture_output=True,
                text=True,
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
        if not output:
            return None
            
        try:
            data = json.loads(output)
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
