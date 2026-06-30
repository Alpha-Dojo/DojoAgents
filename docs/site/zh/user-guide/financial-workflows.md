# 金融工作流

## 适用场景

DojoAgents 面向量化金融分析，常见工作流包括行情查询、行业分析、组合构建、组合验证、报告生成和可视化展示。

## 核心能力

- DojoSDK 工具接入。
- Dashboard financial services 和 store。
- Agent tool result 中的 `resource_changes`，用于驱动前端刷新。
- `viz_blocks`，用于展示表格、K 线、趋势和组合分析结果。
- Harness，用于让 Agent 在金融任务中完成必要步骤后再总结。

## 相关页面

- [DojoSDK Reference](../reference/dojo-sdk.md)
- [Tool Contracts](../reference/tool-contracts.md)
- [Agent Loop 架构](../architecture/agent-loop.md)
- 后续补充：将金融 harness 的细节继续收敛到本页和 Agent Loop 架构页
