# Memory

## 适用场景

Memory 用于跨轮或跨会话保存对话摘要、技能摘要和上下文信息，帮助 Agent 在较长任务中保持连续性。

## 当前模块

| 模块 | 说明 |
| --- | --- |
| `dojoagents/memory/provider.py` | Memory provider 协议 |
| `dojoagents/memory/manager.py` | Memory 管理器 |
| `dojoagents/memory/local_memory.py` | 本地 memory provider |
| `dojoagents/memory/skill_summary.py` | Skill summary provider |

## 使用原则

- 不要把密钥、token 或用户敏感配置写入 memory。
- 长上下文整理应明确区分事实摘要和模型推断。
- 面向 Dashboard/API 暴露时应遵守脱敏策略。

## 深入阅读

见 [Memory 架构](../architecture/memory.md)。

