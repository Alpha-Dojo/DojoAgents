# DojoAgents 声明式插件（Declarative Plugins）集成方案设计

声明式插件（如 `superpowers`）是一种跨平台的、语言无关的插件形式。它通过配置文件定义生命周期钩子（Hooks）与外部 Shell 命令行/脚本的绑定关系，并在智能体运行时通过独立的子进程执行脚本、捕获 `stdout` 输出并将其合并回大模型上下文。

本方案旨在设计如何在 `DojoAgents` 中集成这种声明式插件系统，使平台能够兼容无 Python 源码、纯配置/脚本型的第三方插件。

---

## 一、 核心设计理念

1. **语言无关性 (Polyglot Compatibility)**：插件开发者可以使用 Bash、Node.js、Python 或 Go 编写钩子处理器，只要它们能够读取环境变量并向 `stdout` 输出 JSON 即可。
2. **兼容 superpowers 标准 (Drop-in Compatibility)**：为了能够无缝运行类似 `superpowers` 的插件，`DojoAgents` 的加载器应同时兼容扩展的 `plugin.yaml` 格式和行业通用的 `hooks.json` 映射定义。
3. **环境上下文传递 (Context Piping)**：在调用每个钩子的子进程时，`DojoAgents` 会以环境变量（带 `DOJO_` 前缀，同时也提供通用的平台名）将当前会话的上下文（Session ID, User Message, Tool Args 等）注入子进程的运行环境。
4. **安全沙箱与超时控制 (Isolation & Timeout)**：子进程的运行应配置超时限制（如 5 秒），防止阻塞型脚本挂起核心智能体对话循环。

---

## 二、 目录与声明规范

声明式插件放置于相同的扫描目录（内置 `dojoagents/plugins/built_in/` 或外部 `~/.dojo/plugins/`），但其内部**不包含 `__init__.py`**，而是包含 `plugin.yaml` 和可执行脚本：

### 1. 结构树示例
```text
~/.dojo/plugins/
└── project_guardian/
    ├── plugin.yaml       # 插件描述与钩子声明
    ├── hooks.json        # 兼容 superpowers 格式的钩子映射（可选）
    └── scripts/
        ├── session_start.sh  # 启动钩子脚本
        └── pre_tool.py       # 工具前置拦截脚本
```

### 2. 声明文件 `plugin.yaml` 规范
我们在已有的 `plugin.yaml` 结构中新增 `hooks` 字典：

```yaml
name: project_guardian
version: 1.0.0
description: "声明式安全卫士插件，通过外部脚本监控高危命令"
provides_hooks:
  - on_session_start
  - pre_tool_call
hooks:
  on_session_start:
    command: "bash scripts/session_start.sh"
  pre_tool_call:
    command: "python scripts/pre_tool.py"
    matcher: "^(write_file|delete_file|execute_code)$" # 仅在调用指定工具时触发
```

---

## 三、 运行管道与环境变量绑定

当生命周期钩子被触发时，主引擎将通过 Shell 子进程运行对应的 `command`，运行环境将预装以下上下文变量：

### 1. 环境变量对照表

| 环境变量名 | 作用描述 | 示例值 |
| :--- | :--- | :--- |
| `DOJO_SESSION_ID` / `SESSION_ID` | 当前对话会话标识符 | `sess_129837` |
| `DOJO_USER_MESSAGE` / `USER_MESSAGE`| 用户的输入请求文本 | `"分析 BTC 走势，将图表保存到 charts/"` |
| `DOJO_HOOK_EVENT` | 当前运行的钩子事件名 | `"pre_tool_call"` |
| `DOJO_TOOL_NAME` / `TOOL_NAME` | 即将执行的工具名称（仅工具级钩子提供） | `"execute_code"` |
| `DOJO_TOOL_ARGS` | 即将执行的工具参数（JSON 字符串） | `{"code": "import os; os.system(...)"}` |
| `DOJO_TOOL_CALL_ID` | 大模型分配的工具调用 ID | `"call_98sfd97"` |
| `DOJO_TOOL_RESULT` | 工具返回的输出内容（仅 post_tool 提供） | `"{\"status\": \"success\"}"` |
| `DOJO_DURATION_MS` | 工具耗时毫秒数（仅 post_tool 提供） | `235` |

### 2. 输出 JSON 解析兼容

子进程通过 `stdout` 返回 JSON 结果，`DojoAgents` 按如下格式解析并响应：
*   **对于注入类钩子 (`pre_llm_call`)**：
    支持解析顶级 `additionalContext` 或 `additional_context` 字段，将其拼接入大模型 System Prompt 尾部。
*   **对于拦截类钩子 (`pre_tool_call`)**：
    支持解析 `{"action": "block", "message": "阻断原因"}` 或 `{"decision": "block", "reason": "阻断原因"}`。
*   **对于重写类钩子 (`transform_tool_result` / `transform_llm_output`)**：
    支持解析 `{"result": "新文本"}` 字段，若返回纯文本，则将纯文本直接作为重写内容。

---

## 四、 核心改造 Demo 代码

### 1. 升级后的插件扫描与执行器：`dojoagents/plugins/registry.py` (增量设计)

```python
import subprocess
import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, List

LOGGER = logging.getLogger("dojoagents.plugins")

class DojoPluginRegistry:
    def __init__(self):
        self._plugins = {}
        self._hooks = {}     # Imperative Python callbacks
        self._decl_hooks = {} # Declarative Shell command hooks
        self._tools = []

    def _load_plugin(self, manifest: PluginManifest) -> None:
        init_file = Path(manifest.path) / "__init__.py"
        yaml_file = Path(manifest.path) / "plugin.yaml"
        hooks_json_file = Path(manifest.path) / "hooks.json"
        
        # 1. 解析 yaml 配置文件中的声明式 hooks
        meta = {}
        if yaml_file.exists():
            with open(yaml_file, "r", encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}

        # 2. 如果存在 hooks.json (兼容 superpowers 规范)
        if hooks_json_file.exists():
            try:
                with open(hooks_json_file, "r", encoding="utf-8") as f:
                    hooks_data = json.load(f) or {}
                    meta["hooks"] = hooks_data.get("hooks", {})
            except Exception as e:
                LOGGER.error(f"Failed to load hooks.json in {manifest.name}: {e}")

        # 3. 将声明式钩子保存至注册表
        if "hooks" in meta:
            for hook_name, hook_cfg in meta["hooks"].items():
                # 兼容 superpowers 数组和字典的钩子定义
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
            LOGGER.info(f"Registered declarative hooks from plugin '{manifest.name}'")

        # 4. 如果存在 __init__.py，则继续加载命令式 Python 插件
        if init_file.exists():
            self._load_python_module(manifest)

    def invoke_hook(self, hook_name: str, **kwargs: Any) -> List[Any]:
        results = []
        
        # 1. 首先执行原生的 Python 命令式钩子回调
        callbacks = self._hooks.get(hook_name, [])
        for cb in callbacks:
            try:
                ret = cb(**kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as e:
                LOGGER.error(f"Error in python hook '{hook_name}': {e}", exc_info=True)

        # 2. 执行配置绑定的外部 Shell 声明式钩子
        decl_hooks = self._decl_hooks.get(hook_name, [])
        for hook in decl_hooks:
            # 过滤 matcher 表达式
            if hook["matcher"] and "tool_name" in kwargs:
                import re
                if not re.search(hook["matcher"], kwargs["tool_name"]):
                    continue

            try:
                ret = self._run_shell_hook(hook, hook_name, **kwargs)
                if ret is not None:
                    results.append(ret)
            except Exception as e:
                LOGGER.error(f"Error in declarative hook '{hook_name}' in plugin {hook['plugin_name']}: {e}")
                
        return results

    def _run_shell_hook(self, hook: dict, hook_name: str, **kwargs: Any) -> Any:
        command = hook["command"]
        plugin_path = hook["plugin_path"]
        
        # 构建运行环境变量，融合 kwargs 与前缀变量
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
            
        # 在插件所在的目录下执行 Shell 命令，保证相对路径寻址
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=plugin_path,
                capture_output=True,
                text=True,
                env=env,
                timeout=5.0  # 超时保护防止死锁
            )
        except subprocess.TimeoutExpired:
            LOGGER.warning(f"Hook command '{command}' in {hook['plugin_name']} timed out.")
            return None
            
        if res.returncode != 0:
            LOGGER.error(f"Hook command failed with exit {res.returncode}. stderr: {res.stderr}")
            return None

        # 解析输出内容
        output = res.stdout.strip()
        if not output:
            return None
            
        # 尝试按 JSON 解析
        try:
            data = json.loads(output)
            if isinstance(data, dict):
                # 兼容 superpowers: 提取 additionalContext
                if "additionalContext" in data:
                    return data["additionalContext"]
                if "additional_context" in data:
                    return data["additional_context"]
                # 兼容 superpowers: 提取 veto block 状态
                if "action" in data:
                    return data
                if "decision" in data:
                    return {"action": data["decision"], "message": data.get("reason", "")}
                if "result" in data:
                    return data["result"]
            return data
        except json.JSONDecodeError:
            # 非 JSON 输出，直接返回纯文本作为结果
            return output
```

---

## 五、 Demo 插件：守护卫士 (`project_guardian`)

这是基于该方案的一个完整声明式插件示例，不包含任何 Python 代码，全部由 YAML 配置文件与独立的可执行脚本组成。

### 1. `plugin.yaml`
```yaml
name: project_guardian
version: 1.0.0
description: "这是一个利用 Node.js 编写的安全审计钩子，防范删库等危险操作"
provides_hooks:
  - pre_tool_call
hooks:
  pre_tool_call:
    command: "node scripts/audit.js"
    matcher: "execute_code"
```

### 2. `scripts/audit.js`
```javascript
#!/usr/bin/env node

// 1. 从环境变量中取出模型传入的工具参数
const toolArgsRaw = process.env.DOJO_TOOL_ARGS || '{}';
let toolArgs = {};
try {
  toolArgs = JSON.parse(toolArgsRaw);
} catch (e) {
  process.exit(0); // 无法解析则放行
}

const code = toolArgs.code || '';

// 2. 高危代码分析规则
const maliciousKeywords = [
  'rm -rf',
  'shred',
  'os.remove',
  'shutil.rmtree',
  'drop database',
  '.drop('
];

let isMalicious = false;
let triggeredKeyword = '';

for (const keyword of maliciousKeywords) {
  if (code.toLowerCase().includes(keyword)) {
    isMalicious = true;
    triggeredKeyword = keyword;
    break;
  }
}

// 3. 输出阻断决策给大模型
if (isMalicious) {
  console.log(JSON.stringify({
    decision: 'block',
    reason: `Safety Violation: Code execution blocked due to restricted command pattern '${triggeredKeyword}'.`
  }));
} else {
  console.log(JSON.stringify({
    decision: 'allow'
  }));
}
process.exit(0);
```
