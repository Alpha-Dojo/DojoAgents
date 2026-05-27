# DojoAgents 插件系统升级设计方案与开发文档 (v3 - 独立插件注册表与内置插件目录结构)

本设计方案基于对 Hermes Agent 插件系统架构的研究，结合 DojoAgents 当前的设计（如 `AgentLoop`, `DojoExtensionRegistry`, `ToolExecutor` 等），在 `dojoagents/plugins` 下建立独立的 **DojoPluginRegistry**，并将默认的内置插件归档于 `dojoagents/plugins/built_in/` 下，实现模块化解耦与统一扩展管理。

---

## 一、 新增目录与文件结构说明

本次升级需要在 `DojoAgents` 代码库中添加以下目录和文件：

```text
dojoagents/
└── plugins/
    ├── __init__.py           # 插件模块初始化，暴露全局 Registry 获取方法
    ├── registry.py           # DojoPluginRegistry, PluginContext & Manifest 的实现
    └── built_in/             # 内置插件根目录（内置插件可存放在此目录下）
        ├── __init__.py       # 标记为 Python Package
        └── example_plugin/   # 示例内置插件模板（可选，用于演示开发规范）
            ├── __init__.py   # 插件的注册回调逻辑 (register)
            └── plugin.yaml   # 插件的元数据声明
```

---

## 二、 核心实现细节与文件代码

### 1. `dojoagents/plugins/registry.py` [NEW]
* **作用**：定义插件元数据结构、生命周期钩子管理、以及插件的发现与动态加载机制（包括 `built_in` 插件目录和外部 `~/.dojo/plugins/` 用户插件目录）。

```python
from __future__ import annotations

import importlib.util
import logging
import os
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
        spec = ToolSpec(name=name, schema=schema, handler=handler)
        self._registry._tools.append(spec)
        LOGGER.info(f"Registered tool '{name}' from plugin '{self.manifest.name}'")


class DojoPluginRegistry:
    """独立的插件注册表与管理器"""
    def __init__(self) -> None:
        self._plugins: Dict[str, Any] = {}
        self._hooks: Dict[str, List[Callable]] = {}
        self._tools: List[Any] = []  # 插件注册的自定义工具列表
        self._discovered = False

    def discover_and_load(self) -> None:
        if self._discovered:
            return

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
        if not init_file.exists():
            return

        # 使用命名空间 dojo_plugins. 加载，防止命名冲突
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
            LOGGER.info(f"Successfully registered plugin '{manifest.name}' ({manifest.source})")

    def invoke_hook(self, hook_name: str, **kwargs: Any) -> List[Any]:
        callbacks = self._hooks.get(hook_name, [])
        results = []
        for cb in callbacks:
            try:
                ret = cb(**kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as e:
                LOGGER.error(f"Error in hook '{hook_name}' execution: {e}", exc_info=True)
        return results
```

---

### 2. `dojoagents/plugins/__init__.py` [NEW]
* **作用**：对外暴露方便获取全局 `DojoPluginRegistry` 单例的接口。

```python
from __future__ import annotations

from dojoagents.plugins.registry import DojoPluginRegistry

_global_registry: DojoPluginRegistry | None = None

def get_plugin_registry() -> DojoPluginRegistry:
    """获取并延迟初始化全局插件注册表单例"""
    global _global_registry
    if _global_registry is None:
        _global_registry = DojoPluginRegistry()
        _global_registry.discover_and_load()
    return _global_registry
```

---

### 3. 通用插件开发模板：`dojoagents/plugins/built_in/example_plugin/` [NEW]

这是一个通用的插件模板，展示如何利用 Hooks 和自定义工具编写插件：

#### A. 元数据声明 `plugin.yaml`
```yaml
name: example_plugin
version: 1.0.0
description: "Dojo 通用插件模版。演示如何注册工具和绑定生命周期钩子。"
provides_tools:
  - example_tool
provides_hooks:
  - pre_llm_call
  - transform_llm_output
```

#### B. 主程序入口 `__init__.py`
```python
import json
import logging
from typing import Dict, Any

LOGGER = logging.getLogger("dojo_plugins.built_in.example_plugin")

def example_tool_handler(param: str) -> str:
    """这是一个示例工具处理器"""
    LOGGER.info(f"Executing example tool with param: {param}")
    return json.dumps({"status": "success", "result": f"Processed {param}"}, ensure_ascii=False)


def register(ctx) -> None:
    # 1. 注册自定义工具，供大模型在决策时主动调用
    tool_schema = {
        "name": "example_tool",
        "description": "这是一个供演示使用的示例工具",
        "parameters": {
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": "传入的测试参数"
                }
            },
            "required": ["param"]
        }
    }
    ctx.register_tool(
        name="example_tool",
        schema=tool_schema,
        handler=lambda args, **kwargs: example_tool_handler(args.get("param", ""))
    )

    # 2. 注入 pre_llm_call 钩子，可在大模型生成对话前附加临时上下文
    def on_pre_llm(session_id: str, user_message: str) -> str:
        return "提示：插件已挂载并开始监听本轮对话。"
    
    ctx.register_hook("pre_llm_call", on_pre_llm)

    # 3. 注入 transform_llm_output 钩子，可在最终文本返回用户前修改内容
    def on_transform_output(response_text: str, session_id: str) -> str:
        suffix = "\n\n*提示：此消息已通过插件处理机制。*"
        if suffix not in response_text:
            return response_text + suffix
        return response_text

    ctx.register_hook("transform_llm_output", on_transform_output)
```

---

## 三、 AgentLoop 主体流程集成方式 (loop.py)

我们在 `AgentLoop` 执行阶段通过 `get_plugin_registry()` 单例动态获取并执行相应的 hooks，而不需要硬编码注入复杂的逻辑：

```python
# dojoagents/agent/loop.py 中修改关键流程点：

from dojoagents.plugins import get_plugin_registry

class AgentLoop:
    # __init__ 保持轻量

    async def run(self, request: ChatRequest) -> AgentResponse:
        # 获取插件注册表单例并初始化（自动加载内置及外部插件）
        plugin_registry = get_plugin_registry()

        # 1. 触发 session 启动 hook
        plugin_registry.invoke_hook(
            "on_session_start",
            session_id=request.session_id,
            model=self.config.model,
        )

        messages = await self._build_messages(request)

        # 2. 触发 pre_llm_call 钩子，支持插件注入临时上下文
        pre_results = plugin_registry.invoke_hook(
            "pre_llm_call",
            session_id=request.session_id,
            user_message=request.message,
        )
        for res in pre_results:
            if isinstance(res, str):
                messages[-1]["content"] += f"\n\n[Plugin Context]\n{res}"

        # 收集系统工具
        tool_specs = self._collect_tool_specs()
        # 并入插件动态注册的自定义工具到 LLM 声明中
        for plugin_tool in plugin_registry._tools:
            self.tool_executor.registry.register(plugin_tool)
            tool_specs.append(plugin_tool.schema)

        tool_specs, tool_name_map = self._sanitize_tool_specs(tool_specs)

        for iteration in range(self.config.max_iterations):
            # 3. 触发 pre_api_request
            plugin_registry.invoke_hook(
                "pre_api_request",
                session_id=request.session_id,
                api_call_count=iteration + 1,
                request_messages=messages,
            )

            llm_result = await self.llm_provider.chat(...)

            # 4. 触发 post_api_request
            plugin_registry.invoke_hook(
                "post_api_request",
                session_id=request.session_id,
                api_call_count=iteration + 1,
                llm_result=llm_result,
            )

            # ...工具分发过滤与拦截...
            for call in tool_calls:
                # 5. 触发 pre_tool_call 钩子，允许插件实现安全阻断
                block_signals = plugin_registry.invoke_hook(
                    "pre_tool_call",
                    tool_name=call.name,
                    args=call.arguments,
                    session_id=request.session_id,
                )
                blocked_by_plugin = False
                for sig in block_signals:
                    if isinstance(sig, dict) and sig.get("action") == "block":
                        blocked_by_plugin = True
                        blocked_results.append(ToolResult(
                            call_id=call.id,
                            name=call.name,
                            ok=False,
                            content=sig.get("message", "Blocked by plugin Sentinel"),
                        ))
                        break
                if blocked_by_plugin:
                    continue

                # ...执行正常工具...

            # 6. 执行 post_tool_call 和 transform_tool_result
            # （允许插件监测并改写工具结果）

        # 7. 触发 transform_llm_output 重写大模型最终返回给用户的文本
        final_response = llm_result.content
        output_trans = plugin_registry.invoke_hook(
            "transform_llm_output",
            response_text=final_response,
            session_id=request.session_id,
        )
        for trans in output_trans:
            if isinstance(trans, str):
                final_response = trans
                break

        # 8. 触发 post_llm_call & on_session_end
        plugin_registry.invoke_hook(
            "post_llm_call",
            session_id=request.session_id,
            user_message=request.message,
            assistant_response=final_response,
        )
        plugin_registry.invoke_hook(
            "on_session_end",
            session_id=request.session_id,
            completed=True,
        )

        return AgentResponse(content=final_response, session_id=request.session_id)
```
