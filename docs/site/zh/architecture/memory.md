# Memory 架构

## 目标

Memory 模块为 Agent 提供可插拔的会话记忆、摘要和长期上下文能力。

## 模块

| 模块 | 说明 |
| --- | --- |
| `dojoagents/memory/provider.py` | Provider 协议 |
| `dojoagents/memory/manager.py` | 统一管理器 |
| `dojoagents/memory/local_memory.py` | 本地实现 |
| `dojoagents/memory/skill_summary.py` | Skill summary |

## 安全边界

- 不把 provider secrets 或 API keys 写入 memory。
- 对外展示 memory 内容时需要考虑脱敏。
- 长上下文压缩应保留事实来源和不确定性。

## 深入阅读

- [Session 设计与集成](../development/session-history-design.md)
