# Session 设计与集成

## 概览

DojoAgents 将 session 作为 agent runtime 的一部分管理，而不是交给 dashboard 前端单独持久化。运行时会为每个 `session_id` 创建一个 Strands `SessionManager`，由 Dojo 的 `SessionRepository` 负责落盘，dashboard 只通过接口查询、归档和导出。

这套设计的目标是：

- 让后端成为会话历史的权威来源。
- 让同一个 `session_id` 可以在下一轮对话中自动恢复上下文。
- 让 memory 与 session 历史同步，但不把 exact transcript 混进 memory 存储。
- 让 dashboard 和导出功能复用同一套 runtime session 能力。

## 存储结构

默认 session 根目录：

```text
~/.dojo/agents/strands_sessions
```

每个 session 使用 Strands 兼容目录布局：

```text
session_<session_id>/
├── session.json
├── dojo_session.json
├── dojo_turns.jsonl
├── dojo_memory.json
├── agents/
│   └── agent_<agent_id>/
│       ├── agent.json
│       └── messages/
│           ├── message_0.json
│           ├── message_1.json
│           └── ...
└── multi_agents/
```

职责划分：

- `session.json`、`agent.json`、`message_*.json`：Strands 原生会话和消息存储。
- `dojo_session.json`：Dojo 的 dashboard 查询侧边数据，比如标题、状态、message 数、turn 数、token 状态、memory 状态。
- `dojo_turns.jsonl`：每轮运行的事件、tool trace、usage 快照。
- `dojo_memory.json`：当前 session 关联的 memory 同步结果。

## 配置项

在 `~/.dojo/agents.yaml` 中通过 `sessions` 段配置：

```yaml
sessions:
  enabled: true
  provider: dojo_repository
  root: ~/.dojo/agents/strands_sessions
  agent_id: dojo-agent
  persist_openai_history: true
  sync_memory: true
  export_default_dir: ~/Desktop/dojo-chat-export
```

字段说明：

- `enabled`：是否启用 runtime session。
- `provider`：推荐使用 `dojo_repository`。兼容 `strands_file`，但 dashboard sidecar 能力以 `dojo_repository` 为主。
- `root`：session 根目录。
- `agent_id`：Strands agent 标识，切换后会影响同一 session 的恢复范围。
- `persist_openai_history`：兼容 OpenAI 风格 history 请求时是否继续接受历史消息。
- `sync_memory`：run 完成后是否把本轮结果同步到 memory。
- `export_default_dir`：不显式传目录时的默认导出目录。

## 运行时行为

`/api/chat` 和 `/api/chat/runs` 都会在 runtime 中经过同一套 session 生命周期：

1. `begin_run`：建立或更新 `dojo_session.json`，写入运行中状态。
2. Strands `SessionManager` 恢复该 `session_id` 现有消息。
3. agent 基于当前输入继续执行，不需要前端重复提交整个历史。
4. `finish_run`：刷新 sidecar、记录 turn 事件、同步 memory。
5. 失败或取消时写入 error/cancelled 状态。

推荐约定：

- 前端稳定传入同一个 `session_id`。
- 后端以 session 仓库中的历史为准恢复上下文。
- dashboard 在新一轮 run 中只传当前输入。

## Dashboard 接口

当前推荐使用 `/api/v1` 下的 session 接口：

- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{session_id}`
- `GET /api/v1/chat/sessions/{session_id}/messages`
- `POST /api/v1/chat/sessions/{session_id}/archive`
- `POST /api/v1/chat/sessions/export`

这些接口面向 dashboard 的 session 列表、会话详情、消息历史、归档和全量导出。

兼容接口：

- `GET /api/chat/sessions/{session_id}/tokens`

这个接口仅返回 token ledger 快照，不是完整 session 查询接口。

## 导出

导出接口：

```text
POST /api/v1/chat/sessions/export
```

未指定目录时，导出到：

```text
~/Desktop/dojo-chat-export
```

导出目录包含：

- `sessions.json`
- `messages.jsonl`
- `manifest.json`
- `transcripts/*.md`
- `strands/` 原始会话文件副本

适合做审计、人工回放、离线备份和外部归档。

## 开发注意事项

- 将 `sessions.root` 挂到持久卷，不要放在临时容器层。
- 若 dashboard 会多实例部署，确保多个实例看到同一份 session 存储，或明确做实例级隔离。
- 若启用导出，确认 `export_default_dir` 对运行用户可写。
- 若启用 memory 同步，确认 memory provider 与 session 数据目录一起纳入备份策略。
- 若迁移 `agent_id` 或 `sessions.root`，视为会话恢复边界变化，应先评估已有 session 的可见性。

## 常见问题

### 切换 session 后看不到历史消息

优先检查：

- 前端是否在切换后调用了 `GET /api/v1/chat/sessions/{session_id}/messages`。
- 该 `session_id` 目录下是否已有 `agents/agent_<agent_id>/messages/`。
- `agent_id` 是否发生变化，导致恢复范围不同。

### 新一轮对话没有继承上下文

优先检查：

- 前端是否复用了原来的 `session_id`。
- runtime 是否启用了 `sessions.enabled`。
- `AgentLoop` 是否成功附加了 `session_manager`。

### 导出目录为空或不完整

优先检查：

- 导出目标目录是否可写。
- 目标 session 是否已经完成至少一轮 `finish_run`。
- sidecar 文件是否被外部清理。
