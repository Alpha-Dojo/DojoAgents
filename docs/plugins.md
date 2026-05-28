# DojoAgents 适配 Claude Plugins 设计

DojoAgents 插件系统通过集成 **Native Python-based Adaptation Layer**，完全兼容 Claude Code 的插件生态与配置规范。这使得第三方开发者针对 Claude Code 编写的插件（包括声明式技能、子代理定义、生命周期钩子、MCP/LSP 服务及 Shell 环境变量注入）可以直接安装并运行在 DojoAgents 中。

---

## 1. 架构设计 (Architecture)

以下架构图展示了 `DojoPluginRegistry` 如何识别并加载 Claude-format 插件，并将其声明式配置适配至 DojoAgents 内置的 Runtime 中：

```mermaid
graph TD
    %% Discovery
    subgraph 插件扫描与加载 (Discovery & Load)
        Scanner[Registry Scanner] -->|扫描子目录| Detect{文件检测}
        Detect -->|存在 plugin.yaml| Native[Dojo 原生插件加载]
        Detect -->|存在 plugin.json| ClaudeAdapter[Claude 适配层加载]
    end

    %% Parsing & Adaptation
    subgraph Claude 适配层核心 (Claude Adaptation Layer)
        ClaudeAdapter --> ManifestParser[Manifest 解析与路径解析]
        ManifestParser -->|动态路径替换| RootResolve[${CLAUDE_PLUGIN_ROOT} 替换]
        
        ManifestParser --> SkillsLoader[Skills / Commands 加载器]
        ManifestParser --> AgentsLoader[Agents 目录加载器]
        ManifestParser --> HooksAdapter[Hooks 转换层]
        ManifestParser --> MCPConfig[MCP / LSP 服务管理器]
        ManifestParser --> BinInjector[PATH 环境变量注入器]
    end

    %% Dojo Runtime Mapping
    subgraph Dojo Agents 运行期 (Dojo Runtime)
        SkillsLoader -->|YAML Frontmatter & MD| DojoTools[Dojo System Prompt / Tools]
        AgentsLoader -->|Markdown Frontmatter| DojoSubagents[Dojo Subagents Registry]
        HooksAdapter -->|Stdin JSON Stream Wrapper| DojoLifecycle[Dojo Lifecycle Hooks]
        MCPConfig -->|Subprocess spawning| DojoMCPSystem[Dojo MCP Client System]
        BinInjector -->|Prepend PATH| ShellTool[Dojo Bash/Shell Tool Wrapper]
    end
```

---

## 2. 目录结构与 Manifest 映射

### Claude 插件物理布局
```text
my-first-plugin/
├── .claude-plugin/
│   └── plugin.json           # 描述插件元数据的主 manifest 文件
├── skills/
│   └── hello/
│       └── SKILL.md          # 技能描述（包含 YAML 前导元数据与指令内容）
├── agents/
│   └── reviewer.md           # 自定义子代理描述
├── hooks/
│   └── hooks.json            # 声明式钩子规则
├── .mcp.json                 # MCP 服务运行配置
├── .lsp.json                 # LSP 服务映射规则
├── bin/                      # 可执行脚本目录（启动时自动加入 Bash 执行路径）
└── settings.json             # 默认用户配置覆盖
```

### Manifest 解析策略
1. **统一注册入口**：除了现有的 `plugin.yaml`，扫描时如果发现 `.claude-plugin/plugin.json` 或 `plugin.json`，则触发 Claude 兼容模式。
2. **元数据适配**：解析 `name`、`description`、`version`、`author` 等关键字段，映射到 Dojo 的 `PluginManifest` 数据模型。
3. **相对路径解析**：若 manifest 或子配置文件中含有相对路径（如 `"lspServers": "./.lsp.json"`），加载器会结合插件在系统中的绝对根路径，将其转换为完整绝对路径。
4. **占位符解析**：配置文件中所有的 `${CLAUDE_PLUGIN_ROOT}` 或 `${DOJO_PLUGIN_ROOT}` 变量，在加载期将被动态替换为当前插件目录的绝对物理路径。

---

## 3. 生命期钩子转换层 (Hooks Adapter)

Claude 插件允许在特定事件发生时，通过 `stdin` 接受 JSON 事件上下文并调用外部 shell 命令。Dojo 适配层负责在底层钩子调用时进行翻译和序列化：

### 钩子事件对照表

| Dojo 触发事件 | 翻译对应的 Claude 事件名 | 传给 Stdin 的 JSON 键值 |
| :--- | :--- | :--- |
| `on_session_start` | `SessionStart` | `event`, `session_id`, `cwd` |
| `pre_llm_call` | `UserPromptSubmit` | `event`, `session_id`, `user_message` |
| `pre_tool_call` | `PreToolUse` | `event`, `session_id`, `tool_name`, `tool_input` (参数字典) |
| `post_tool_call` | `PostToolUse` | `event`, `session_id`, `tool_name`, `tool_input`, `tool_output` (执行结果) |
| `on_session_end` | `SessionEnd` | `event`, `session_id` |

### 运行时控制流适配
* **输入流传递 (Stdin payload)**：Dojo 会将转义后的 JSON 字符串以标准输入管道方式写入 hook command 进程中。
* **执行拦截 (Block decision)**：当触发 `PreToolUse` 类型的钩子且命令向标准输出（`stdout`）打印了 `{"decision": "block", "reason": "..."}` 时，DojoAgents 将拦截当前的工具调用，并将拦截原因反馈给 LLM 或提示用户。
* **额外上下文附加**：如果 hook command 执行完成后输出 `{"additionalContext": "..."}`，该内容将被作为背景上下文动态加入当前的 Prompt 链条中。

---

## 4. 核心功能组件适配细节

### 1. 技能 (Skills) 与 代理 (Agents) 的加载与解析
* **Skills**：扫描 `skills/<name>/SKILL.md`，提取 frontmatter 中的 `description` 并将其作为模型调用的 Tool 定义。在模型需要触发该技能时，将 `SKILL.md` 的内容动态注入系统 Prompt。
* **Agents**：解析 `agents/*.md` 的前导参数（如 `model`, `effort`, `maxTurns`, `disallowedTools` 等），转换为 Dojo 的子代理架构，并在 `invoke_subagent` 接口中对大模型暴露。

### 2. MCP 与 LSP 服务的自启动管理
* **MCP Servers**：读取 `.mcp.json` 并调用 Dojo 内置的 MCP 控制器。拉起子进程（例如 Node/Python 运行进程），并将 MCP 服务所提供的工具注册进当前 Agent 实例。
* **LSP Servers**：读取 `.lsp.json` 映射配置，当 Agent 对特定类型文件进行深度代码导航（Go-to-definition, Find references 等）时激活服务以配合代码分析。

### 3. 可执行环境劫持 (PATH Injection)
* 当插件被启用时，DojoAgents 的 `ShellTool` 会修改环境执行上下文，在 `os.environ["PATH"]` 头部 prepend 当前插件的 `bin/` 目录。
* 这使得插件中的可执行脚本（例如定制的格式化工具、静态分析工具）在被 Agent 以命令行执行时可以“像全局原生命令一样”直接被调用。

---

## 5. 实施文化与指导原则 (Implementation Culture)

为了保证这一套适配方案能够高质量实施并长期平稳运行，开发与维护时必须遵循以下原则：

1. **绝对向后兼容 (Strict Conformance)**：在适配层编写的所有 JSON/Markdown 序列化解析逻辑，都必须遵循 Claude Code 的规范要求。任何现存的 Claude 插件都可以“零配置修改”直接运行在 DojoAgents 中。
2. **单点故障隔离 (Fault Isolation & Sandboxing)**：单个插件由于依赖缺失、脚本抛错或配置损坏导致初始化失败时，Dojo 必须捕获该异常并降级记录日志，严禁让个别插件的错误导致整个 Dojo 运行时崩溃或死锁。
3. **环境无关性与路径安全**：对于所有文件操作及子进程唤起，必须依赖动态计算的 `CLAUDE_PLUGIN_ROOT` 路径。避免硬编码以防止在跨平台（macOS / Linux）或不同虚拟环境（Virtualenv / Docker）下发生路径找不到的错误。
4. **日志追踪透明化**：插件拉起的后台 Monitor、MCP 服务以及 Hook command 的 stderr 输出必须独立记录并输出至 Dojo 审计日志中，以便于在调试模式下能快速排查插件冲突。

---

## 6. 对话式插件管理与使用方案 (Conversational Plugin Management & Usage)

为了让用户能够通过与 DojoAgents 对话或使用内置 Slash 命令直接管理及使用插件，Dojo 引入了**对话式插件管理机制**。该设计参考了 `hermes-agent` 的模块化插件管理理念，并将其适配到 Dojo 的工具调用（Tool Calling）与运行时生命周期中。

### 1. 功能设计 (Functionality Design)

1. **使用插件 (Using Plugins via Chat)**
   - 插件被成功加载后，其注册的自定义工具（Tools）与技能（Skills）会自动并入 Agent 的大脑索引中。
   - 用户只需在对话中描述他们想做的事情（例如：“使用 review-assistant 插件帮我审查这个 PR”），Agent 就会自动识别并调用对应插件提供的工具。

2. **列表插件 (List Plugins)**
   - **对话方式**：Agent 拥有一个内置工具 `list_plugins`。当用户在聊天中询问“我安装了哪些插件？”或“查看插件列表”时，Agent 将调用此工具并把结果渲染为 Markdown 表格回复用户。
   - **命令方式**：终端用户可以直接输入 `/plugins` 或 `/plugins list`。

3. **删除插件 (Delete Plugins)**
   - **对话方式**：Agent 拥有一个内置工具 `delete_plugin`。当用户发出指令（例如：“删除 reviewer 插件”）时，Agent 将调用该工具执行物理删除。
   - **命令方式**：终端用户可以直接输入 `/plugins delete <name>`。

---

### 2. 接口设计 (API & Tool Schemas)

#### A. 插件列表工具 (`list_plugins`)
* **名称 (Name)**: `list_plugins`
* **描述 (Description)**: List all installed user plugins (~/.dojo/plugins) and built-in plugins, showing their name, version, status, and capabilities.
* **参数 (Parameters)**: 无 (Empty object)
* **返回值 (Return)**: 包含所有插件元数据的 JSON 数组。

#### B. 插件删除工具 (`delete_plugin`)
* **名称 (Name)**: `delete_plugin`
* **描述 (Description)**: Delete an installed plugin from the user plugins directory by its name.
* **参数 (Parameters)**:
  * `name` (string, required): The name of the plugin directory to delete.
* **安全防护 (Safety Guards)**:
  * **路径遍历拦截**：防御 `../` 或绝对路径参数，目标路径必须严格限制在 `~/.dojo/plugins/` 目录内。
  * **删除确认机制**：默认在删除前通过交互式终端向用户发起二次确认提示，或在非交互式/IM网关场景下由 Agent 自动向用户反馈确认消息。

---

### 3. 命令调度与执行流 (Slash Command & Dispatching)

```
[ 用户输入 /plugins list ] ──> [ CLI 命令行/网关路由器 ] ──> [ 调用 Registry.list_plugins() ] ──> [ 格式化 Rich 表格输出 ]
[ 用户输入 "帮我删掉 review" ] ──> [ Agent 识别意图 ] ──> [ 触发 Tool Call: delete_plugin ] ──> [ 安全校验 ] ──> [ 执行 shutil.rmtree ]
```

1. **命令行路由**：在 Dojo CLI 或 WeChat 网关命令分发中心，增加 `canonical == "plugins"` 分支。
2. **安全隔离**：内置插件（`dojoagents/plugins/built_in`）为系统级别，只读且不支持被 `delete_plugin` 工具物理删除（调用时将返回 "Built-in plugins cannot be deleted" 错误）。
3. **动态重载**：在启用或删除插件后，Agent 会提示用户运行 `/reload-plugins`（或自动在后台触发 `discover_and_load(force=True)`）以热重载插件注册表，使改动即时生效。

