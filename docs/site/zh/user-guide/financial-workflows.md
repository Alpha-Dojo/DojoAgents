# 金融工作流

## 适用场景

DojoAgents 面向量化金融分析，常见工作流包括行情查询、行业分析、组合构建、组合验证、报告生成和可视化展示。

## 核心能力

- DojoSDK 工具接入。
- Dashboard financial services 和 store。
- Agent tool result 中的 `resource_changes`，用于驱动前端刷新。
- `viz_blocks`，用于展示表格、K 线、趋势和组合分析结果。
- Harness，用于让 Agent 在金融任务中完成必要步骤后再总结。

## 推荐路径

1. 先通过 [模型配置](../getting-started/model-configuration.md) 配好 provider。
2. 启动 [Dashboard](dashboard.md)，确认金融数据 store 能正常加载。
3. 用自然语言提出任务，例如市场概览、行业对比、ticker 分析或组合诊断。
4. 让 Agent 通过工具读取数据；前端根据 `viz_blocks` 展示结构化结果。
5. 如果工具改变了组合或 session 数据，前端根据 `resource_changes` 刷新对应资源。

## 相关页面

- [DojoSDK Reference](../reference/dojo-sdk.md)
- [Tool Contracts](../reference/tool-contracts.md)
- [Agent Loop 架构](../architecture/agent-loop.md)
