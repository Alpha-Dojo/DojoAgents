# Session Context Token Tracking & Memory Architecture

## 1. 背景与目标 (Context & Goal)

当前 `DojoAgents` 的上下文压缩机制 (`ContextCompressor`) 是基于固定的 Token 数量阈值（默认 15000）进行粗略计算和中间消息摘要。为了提供更精细的上下文管理和持久化的长期记忆能力，我们需要引入以下功能：
1. **Token 实时统计**：计算当前 Session 的上下文 Token 已用量和剩余量。
2. **基于比例的阈值触发**：当上下文使用量达到 Session 总 Token 预算的指定阈值（默认 90%）时，自动触发上下文整理和记忆存储。
3. **插件化的记忆系统 (Memory System)**：参考 `hermes-agent` 的实现，将整理出的上下文摘要和关键事实持久化到长期记忆中，支持不同后端的记忆插件（例如本地文件、向量数据库等）。

## 2. 核心架构设计 (Architecture Design)

### 2.1 Token 追踪模块 (Token Tracking)
在 `agent/runtime.py` 或 `agent/loop.py` 中引入准确的 Token 追踪：
- **SessionMaxTokens**: 当前 Session 允许的最大上下文 Token 数量（由所选模型决定，可通过页面配置）。
- **UsedTokens**: 当前历史消息的总 Token 估算/精确计算量。
- **RemainingTokens**: `SessionMaxTokens - UsedTokens`。
- **UI 暴露**: 每次 Agent 交互循环返回当前 `used_tokens` 和 `remaining_tokens`，前端可展示进度条。

### 2.2 记忆整理触发器 (Memory Trigger)
在 `agent/compressor.py` 的现有压缩逻辑基础上重构：
- 配置 `threshold_ratio`（默认 0.9）。
- 当 `UsedTokens > SessionMaxTokens * threshold_ratio` 时，触发 **Memory Consolidation (记忆整理)** 流程。

### 2.3 插件化记忆提供者 (Pluggable Memory Provider)
设计 `MemoryProvider` 抽象基类。参考 `hermes-agent`，记忆系统支持插件化加载：
```python
class MemoryProvider(ABC):
    @abstractmethod
    async def save_memory(self, session_id: str, content: str, metadata: dict = None):
        """将整理出的上下文关键信息存储到持久化记忆中"""
        pass

    @abstractmethod
    async def retrieve_memory(self, session_id: str, query: str) -> str:
        """在新回合开始时，检索相关的历史记忆"""
        pass
```

默认提供一个基于本地存储的实现 (e.g., `LocalFileMemoryProvider`)，类似于 `hermes-agent` 中基于 markdown 或 sqlite 的简单记忆实现。

## 3. 运行流程 (Execution Flow)

1. **User Message**: 用户发送消息，加入当前会话上下文。
2. **Token Check**: 
   - `ContextCompressor` 计算当前 Token 数量。
   - 检查 `used_tokens >= max_tokens * 0.9`。
3. **Consolidation (如果超阈值)**:
   - 提取中间回合的对话历史。
   - LLM 生成两部分内容：
     1. **Session Summary**: 用于放在系统提示词中的超短压缩摘要（保留即时上下文）。
     2. **Long-term Facts/Memories**: 提取出的人物偏好、核心事实、长期任务状态等。
   - 调用 `MemoryProvider.save_memory()` 保存 Long-term Facts。
   - 清理多余的消息，将 Session Summary 替换进上下文。
4. **LLM Generation**: 携带精简后的上下文和检索出的关联记忆（如果有），调用主模型生成回答。

## 4. 目录结构变更 (Directory Structure Changes)

- `dojoagents/agent/memory/`: 新增目录，用于存放记忆相关的核心接口和默认插件。
  - `__init__.py`
  - `provider.py` (MemoryProvider 抽象类)
  - `local_memory.py` (默认的本地记忆插件)
  - `manager.py` (记忆插件加载与生命周期管理)
- `dojoagents/agent/compressor.py`: 修改以支持按比例触发和调用 `MemoryManager` 存储记忆。
- `dojoagents/agent/models.py`: 更新数据模型，在 State 或返回结果中增加 `used_tokens` 和 `remaining_tokens` 字段。
