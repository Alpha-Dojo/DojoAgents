# Harness Runtime and Sessions

Each DojoAgents Agent instance is bound to exactly one Harness instance; there is no primary Harness. Core provides the generic AgentLoop, ToolExecutor, Sandbox, lifecycle, and SessionService. A Harness owns one scenario's identity, prompts, skills, tools, memory, policies, tasks/pipelines, presenters, services, and surface adapters.

The financial Harness is the default:

```yaml
harness:
  id: financial
  factory: dojoagents.harnesses.built_in.financial:create_harness
```

Downstream projects may implement `AgentHarness.configure/startup/shutdown` or use a constrained `dojoagents/v1alpha1` manifest that references component factories. Manifests cannot contain SQL, shell commands, or a business-control DSL; every declaration still passes HarnessBuilder conflict and dependency validation.

Online hosts must map verified credentials to `SessionPrincipal(tenant_id, user_id, roles)`. SessionStore, BlobStore, runs/events, checkpoints, and objects are principal-scoped. A request body or query parameter cannot override the authenticated principal. File storage is built in; MySQL, PostgreSQL, and object storage are supplied by downstream factories and verified with the external conformance gate.

```python
store = ConfigStore("agents.yaml")
runtime = await Runtime.create(store, host="api")
try:
    response = await runtime.agent.run(request)
finally:
    await runtime.shutdown()
```
