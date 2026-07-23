# Harness Runtime 与 Session

DojoAgents 中每个 Agent 实例只绑定一个 Harness 实例，不存在“主 Harness”。Core 提供通用 AgentLoop、ToolExecutor、Sandbox、生命周期和 SessionService；Harness 负责单一场景的 identity、prompt、skills、tools、memory、policy、task/pipeline、presenter、service 与 surface。

默认金融 Harness：

```yaml
harness:
  id: financial
  factory: dojoagents.harnesses.built_in.financial:create_harness
  config:
    data_root: ~/.dojo/dashboard-data
    portfolio_data_root: ~/.dojo/data
```

外部项目可实现 `AgentHarness.configure/startup/shutdown`，或使用 `dojoagents/v1alpha1` manifest 引用受约束的组件 factory。manifest 不支持 SQL、shell 或业务控制流 DSL；所有组件仍经过 HarnessBuilder 的 ID、依赖、tool name 和 exclusive matcher 校验。

在线入口必须把已验证身份映射为 `SessionPrincipal(tenant_id, user_id, roles)`。SessionStore、BlobStore、run/event、checkpoint 和 object 操作都按 principal scope；请求 body/query 中的 `user` 不能覆盖认证身份。file 是默认后端，MySQL/PostgreSQL/对象存储由项目 factory 注入并运行外部 conformance gate。

Python 使用方式：

```python
store = ConfigStore("agents.yaml")
runtime = await Runtime.create(store, host="api")
try:
    response = await runtime.agent.run(request)
finally:
    await runtime.shutdown()
```
