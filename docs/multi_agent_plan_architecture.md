# Multi-Agent & Plan Architecture Design for DojoAgents

## Context

DojoAgents is currently a **single-agent** system: one `AgentLoop` instance processes a `ChatRequest`, calls tools, and returns an `AgentResponse`. The architecture is built on `strands-agents` with a rich hook/plugin system, DojoExtension protocol, and memory providers.

**Goal**: Introduce **multi-agent orchestration** and **plan-driven execution** capabilities that activate automatically when the agent encounters key events (complexity signals, multi-step tasks, quant workflow triggers).

---

## Part 1: Multi-Agent Architecture Design

### 1.1 Core Concept — Hierarchical Agent Pool

```
┌─────────────────────────────────────────────────┐
│              OrchestratorAgent                    │
│  (Planning, Routing, Synthesis, Review)          │
├─────────────────────────────────────────────────┤
│         ┌──────────┐  ┌───────────┐             │
│         │ Worker A │  │ Worker B  │  ...        │
│         │(Analyst) │  │(Coder)    │             │
│         └──────────┘  └───────────┘             │
├─────────────────────────────────────────────────┤
│           SharedMemory / PlanState               │
└─────────────────────────────────────────────────┘
```

- **Orchestrator**: The main agent that receives the user request. It decides whether to handle directly or delegate to specialist sub-agents.
- **Workers**: Specialized agent instances (each is a full `AgentLoop` with different system prompts, tool sets, and constraints).
- **SharedMemory**: Cross-agent state via a `PlanStateProvider` (new MemoryProvider implementation).

### 1.2 Data Models

```python
# dojoagents/multi_agent/models.py

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    ANALYST = "analyst"        # Market research, data analysis
    IMPLEMENTER = "implementer"  # Code generation, strategy coding
    REVIEWER = "reviewer"      # QA, validation, backtesting
    SPECIALIST = "specialist"  # Custom domain-specific roles

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class AgentSpec:
    """Defines a worker agent's configuration."""
    role: AgentRole
    name: str
    system_prompt_override: str = ""
    model: str | None = None           # Override orchestrator's model
    allowed_tools: list[str] = field(default_factory=list)  # Empty = all
    disallowed_tools: list[str] = field(default_factory=list)
    max_iterations: int = 50

@dataclass
class SubTask:
    """A unit of work delegated to a worker agent."""
    id: str
    title: str
    description: str
    assigned_to: AgentRole
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = field(default_factory=list)
    result: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentMessage:
    """Inter-agent communication message."""
    from_agent: str
    to_agent: str
    content: str
    message_type: str = "task_result"  # task_result, question, handoff, status
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 1.3 Agent Pool & Factory

```python
# dojoagents/multi_agent/pool.py

from __future__ import annotations
from typing import Any

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, AgentResponse
from dojoagents.multi_agent.models import AgentSpec, AgentRole

class AgentPool:
    """Manages a pool of specialized agent instances."""
    
    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._agents: dict[str, AgentLoop] = {}
        self._specs: dict[str, AgentSpec] = {}
    
    def register_agent(self, spec: AgentSpec) -> None:
        """Register an agent specification (lazy instantiation)."""
        self._specs[spec.name] = spec
    
    def get_or_create(self, name: str) -> AgentLoop:
        """Get existing agent or create from spec."""
        if name not in self._agents:
            spec = self._specs[name]
            self._agents[name] = self._create_agent(spec)
        return self._agents[name]
    
    def _create_agent(self, spec: AgentSpec) -> AgentLoop:
        """Create a new AgentLoop instance with spec overrides."""
        from dojoagents.agent.runtime import Runtime
        # Clone tool registry with filtered tools
        tool_registry = self._runtime.agent.tool_executor.registry.clone()
        if spec.disallowed_tools:
            for tool_name in spec.disallowed_tools:
                tool_registry.remove(tool_name)
        
        return AgentLoop(
            llm_provider=self._runtime.agent.llm_provider,
            tool_executor=ToolExecutor(tool_registry, self._runtime.agent.tool_executor.policy),
            skill_manager=self._runtime.agent.skill_manager,
            memory_manager=self._runtime.agent.memory_manager,
            extension_registry=self._runtime.agent.extension_registry,
            config=self._runtime.config.agent,  # Can override model here
        )
    
    async def invoke(self, name: str, request: ChatRequest) -> AgentResponse:
        """Invoke a specific agent by name."""
        agent = self.get_or_create(name)
        return await agent.run(request)
```

### 1.4 Orchestrator — Delegation via Tool

The orchestrator delegates to sub-agents through a **`delegate_task` tool** exposed to the LLM:

```python
# dojoagents/multi_agent/tools.py

from dojoagents.tools.registry import ToolSpec

def get_delegation_tool_spec(pool: AgentPool) -> ToolSpec:
    """Tool that lets the orchestrator delegate subtasks to workers."""
    
    async def delegate_handler(
        agent_role: str,
        task_description: str,
        context: str = "",
        **kwargs
    ) -> str:
        from dojoagents.agent.models import ChatRequest
        request = ChatRequest(
            message=f"[Context]\n{context}\n\n[Task]\n{task_description}",
            user_id="orchestrator",
            session_id=f"sub-{agent_role}-{uuid4().hex[:8]}",
            channel="internal",
        )
        response = await pool.invoke(agent_role, request)
        return response.content
    
    return ToolSpec(
        name="delegate_task",
        description="Delegate a subtask to a specialist agent. Use when the task requires specialized analysis, coding, or review.",
        parameters={
            "type": "object",
            "properties": {
                "agent_role": {
                    "type": "string",
                    "enum": ["analyst", "implementer", "reviewer"],
                    "description": "The specialist agent to delegate to"
                },
                "task_description": {
                    "type": "string",
                    "description": "Clear description of what the agent should accomplish"
                },
                "context": {
                    "type": "string",
                    "description": "Relevant context from prior analysis or plan"
                }
            },
            "required": ["agent_role", "task_description"]
        },
        handler=delegate_handler
    )
```

### 1.5 Event-Driven Activation

Multi-agent mode activates via **plugin hooks** that detect complexity:

```python
# dojoagents/multi_agent/triggers.py

COMPLEXITY_TRIGGERS = [
    # Pattern-based triggers
    {"pattern": r"(analyze|research|investigate).+(and|then).+(implement|build|create)", "confidence": 0.8},
    {"pattern": r"(backtest|optimize).+(strategy|portfolio)", "confidence": 0.9},
    {"pattern": r"(compare|evaluate).+multiple", "confidence": 0.7},
]

TOOL_RESULT_TRIGGERS = [
    # When tool results indicate multi-step workflows needed
    {"tool": "dojo_market_data", "result_pattern": r"multiple_assets|large_dataset", "action": "spawn_analyst"},
    {"tool": "code_execution", "result_pattern": r"error|failed", "action": "spawn_reviewer"},
]

class MultiAgentTriggerHook:
    """Plugin hook that detects when to activate multi-agent orchestration."""
    
    def __init__(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator
    
    def on_pre_llm_call(self, user_message: str, session_id: str, **kwargs) -> str | None:
        """Inject orchestration context if complexity detected."""
        import re
        for trigger in COMPLEXITY_TRIGGERS:
            if re.search(trigger["pattern"], user_message, re.IGNORECASE):
                return self._orchestrator.get_orchestration_prompt()
        return None
    
    def on_post_tool_call(self, tool_name: str, result: str, session_id: str, **kwargs) -> None:
        """React to tool results that suggest multi-agent needed."""
        import re
        for trigger in TOOL_RESULT_TRIGGERS:
            if trigger["tool"] == tool_name:
                if re.search(trigger["result_pattern"], result, re.IGNORECASE):
                    self._orchestrator.activate(trigger["action"], session_id)
```

---

## Part 2: Plan Architecture Design

### 2.1 Core Concept — Plan as First-Class Entity

A **Plan** is a structured execution blueprint that the agent creates before complex operations. Plans are:
- Created by the Orchestrator when complexity is detected
- Stored in PlanState (memory provider)
- Executed step-by-step with checkpoints
- Revisable based on intermediate results

### 2.2 Plan Data Models

```python
# dojoagents/planning/models.py

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from datetime import datetime

class PlanStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"  
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVISED = "revised"

class StepType(str, Enum):
    ANALYSIS = "analysis"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    DECISION = "decision"      # Requires LLM reasoning
    DELEGATION = "delegation"  # Delegates to sub-agent

@dataclass
class PlanStep:
    id: str
    title: str
    description: str
    step_type: StepType
    depends_on: list[str] = field(default_factory=list)
    assigned_agent: str = "orchestrator"
    status: str = "pending"
    result: str = ""
    tools_needed: list[str] = field(default_factory=list)
    acceptance_criteria: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class Plan:
    id: str
    title: str
    objective: str
    steps: list[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    context: dict[str, Any] = field(default_factory=dict)
    revision_history: list[dict[str, Any]] = field(default_factory=list)
    
    def next_actionable_steps(self) -> list[PlanStep]:
        """Return steps whose dependencies are all completed."""
        completed_ids = {s.id for s in self.steps if s.status == "completed"}
        return [
            s for s in self.steps
            if s.status == "pending" and all(d in completed_ids for d in s.depends_on)
        ]
    
    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)
```

### 2.3 Plan Execution Engine

```python
# dojoagents/planning/engine.py

from __future__ import annotations
from typing import Any

from dojoagents.planning.models import Plan, PlanStep, PlanStatus, StepType
from dojoagents.multi_agent.pool import AgentPool
from dojoagents.agent.models import ChatRequest, AgentResponse

class PlanExecutionEngine:
    """Executes a plan step-by-step, coordinating with the agent pool."""
    
    def __init__(self, pool: AgentPool, plan_store: PlanStateStore) -> None:
        self._pool = pool
        self._store = plan_store
    
    async def execute_plan(self, plan: Plan, session_id: str) -> Plan:
        """Execute plan steps respecting dependencies."""
        plan.status = PlanStatus.EXECUTING
        self._store.save(plan)
        
        while not plan.is_complete():
            actionable = plan.next_actionable_steps()
            if not actionable:
                plan.status = PlanStatus.FAILED
                break
            
            # Execute actionable steps (could be parallel in future)
            for step in actionable:
                step.status = "in_progress"
                try:
                    result = await self._execute_step(step, plan, session_id)
                    step.result = result
                    step.status = "completed"
                except Exception as e:
                    step.result = str(e)
                    step.status = "failed"
                    plan.status = PlanStatus.FAILED
                    break
            
            self._store.save(plan)
        
        if plan.is_complete():
            plan.status = PlanStatus.COMPLETED
        self._store.save(plan)
        return plan
    
    async def _execute_step(self, step: PlanStep, plan: Plan, session_id: str) -> str:
        """Execute a single plan step."""
        # Build context from completed dependencies
        dep_results = {
            s.id: s.result for s in plan.steps 
            if s.id in step.depends_on and s.status == "completed"
        }
        
        context = f"Plan: {plan.title}\nObjective: {plan.objective}\n"
        context += f"Prior results: {dep_results}\n"
        
        if step.step_type == StepType.DELEGATION:
            request = ChatRequest(
                message=f"{context}\n\nTask: {step.description}",
                user_id="plan_engine",
                session_id=f"plan-{plan.id}-{step.id}",
                channel="internal",
            )
            response = await self._pool.invoke(step.assigned_agent, request)
            return response.content
        else:
            # Orchestrator handles analysis/decision/validation steps
            request = ChatRequest(
                message=f"{context}\n\nExecute step: {step.title}\n{step.description}",
                user_id="plan_engine",
                session_id=session_id,
                channel="internal",
            )
            response = await self._pool.invoke("orchestrator", request)
            return response.content
```

### 2.4 Plan Creation Tool (exposed to agent)

```python
# dojoagents/planning/tools.py

def get_plan_tools(engine: PlanExecutionEngine) -> list[ToolSpec]:
    """Tools that let the agent create and manage plans."""
    
    async def create_plan_handler(
        title: str, objective: str, steps: list[dict], **kwargs
    ) -> str:
        plan = Plan(
            id=uuid4().hex[:8],
            title=title,
            objective=objective,
            steps=[PlanStep(**s) for s in steps],
        )
        engine._store.save(plan)
        return f"Plan '{title}' created with {len(steps)} steps. ID: {plan.id}"
    
    async def execute_plan_handler(plan_id: str, **kwargs) -> str:
        plan = engine._store.get(plan_id)
        result = await engine.execute_plan(plan, session_id=kwargs.get("session_id", ""))
        return f"Plan '{plan.title}' execution {result.status.value}. " + \
               "\n".join(f"  - {s.title}: {s.status}" for s in result.steps)
    
    async def revise_plan_handler(plan_id: str, revision: str, **kwargs) -> str:
        plan = engine._store.get(plan_id)
        plan.revision_history.append({"reason": revision, "timestamp": datetime.utcnow().isoformat()})
        plan.status = PlanStatus.REVISED
        engine._store.save(plan)
        return f"Plan '{plan.title}' marked for revision: {revision}"
    
    return [
        ToolSpec(name="create_plan", description="Create a structured execution plan for a complex task", 
                 parameters={...}, handler=create_plan_handler),
        ToolSpec(name="execute_plan", description="Execute an approved plan step-by-step",
                 parameters={...}, handler=execute_plan_handler),
        ToolSpec(name="revise_plan", description="Revise an existing plan based on new information",
                 parameters={...}, handler=revise_plan_handler),
    ]
```

### 2.5 Plan Activation Triggers

Plans are automatically triggered by these events:

| Event | Trigger Condition | Action |
|-------|------------------|--------|
| User message complexity | Multi-step request detected (regex + token count > threshold) | Create plan before execution |
| Quant workflow start | `request.quant` is not None with `workflow_type = "backtest"` | Auto-generate backtest plan |
| Tool failure cascade | 2+ consecutive tool failures in same session | Pause, create recovery plan |
| Scheduled job with `plan: true` | Job config has `plan: true` flag | Create and execute plan |
| Plugin hook signal | `pre_llm_call` hook returns `{"action": "plan"}` | Trigger plan creation |

```python
# dojoagents/planning/triggers.py

class PlanActivationHook:
    """Detects when automatic plan creation should be triggered."""
    
    COMPLEXITY_THRESHOLD = 100  # tokens in user message
    MULTI_STEP_PATTERNS = [
        r"(first|step 1|phase 1).+(then|next|after)",
        r"(create|build|develop).+plan",
        r"(backtest|optimize|analyze).+(multiple|several|all)",
    ]
    
    def should_create_plan(self, request: ChatRequest) -> bool:
        """Determine if a plan should be auto-created."""
        # 1. Explicit plan request
        if "plan" in request.message.lower()[:50]:
            return True
        
        # 2. Quant backtest workflow
        if request.quant and request.quant.workflow_type == "backtest":
            return True
        
        # 3. Multi-step complexity detection
        import re
        for pattern in self.MULTI_STEP_PATTERNS:
            if re.search(pattern, request.message, re.IGNORECASE):
                return True
        
        # 4. Message length heuristic
        if len(request.message.split()) > self.COMPLEXITY_THRESHOLD:
            return True
        
        return False
```

---

## Part 3: Integration Architecture

### 3.1 New Module Structure

```
dojoagents/
├── multi_agent/
│   ├── __init__.py
│   ├── models.py          # AgentSpec, SubTask, AgentMessage
│   ├── pool.py            # AgentPool, agent factory
│   ├── orchestrator.py    # Orchestration logic
│   ├── tools.py           # delegate_task tool
│   └── triggers.py        # Event-driven activation
├── planning/
│   ├── __init__.py
│   ├── models.py          # Plan, PlanStep, PlanStatus
│   ├── engine.py          # PlanExecutionEngine
│   ├── store.py           # PlanStateStore (persistence)
│   ├── tools.py           # create_plan, execute_plan tools
│   └── triggers.py        # PlanActivationHook
```

### 3.2 Integration Points with Existing Code

| Existing Component | Integration Method | Change Scope |
|---|---|---|
| `AgentLoop.run()` | Add pre-check: if `PlanActivationHook.should_create_plan()`, inject plan tools | Minimal (5-10 lines) |
| `Runtime.from_config_store()` | Register `AgentPool` + `PlanExecutionEngine` + plan/delegation tools | ~20 lines added |
| `DojoPluginRegistry` | Register `MultiAgentTriggerHook` + `PlanActivationHook` as Python hooks | Via plugin system |
| `AgentsConfig` | Add `MultiAgentConfig` and `PlanConfig` dataclasses | New config fields |
| `MemoryManager` | Add `PlanStateProvider` for plan persistence | New provider |
| `ScheduledJob` | Add optional `plan: bool` field to auto-plan scheduled tasks | 1 field addition |

### 3.3 Config Extension

```python
# Addition to dojoagents/config/models.py

@dataclass(frozen=True)
class MultiAgentConfig:
    enabled: bool = False
    max_workers: int = 3
    default_agents: list[dict[str, Any]] = field(default_factory=lambda: [
        {"role": "analyst", "name": "analyst"},
        {"role": "implementer", "name": "implementer"},
        {"role": "reviewer", "name": "reviewer"},
    ])

@dataclass(frozen=True)
class PlanConfig:
    enabled: bool = False
    auto_plan_threshold: int = 100  # word count trigger
    plan_store_path: str = "~/.dojo/agents/plans"
    max_plan_steps: int = 10
```

### 3.4 Activation Flow Diagram

```
User Message → AgentLoop.run()
    │
    ├─ PlanActivationHook.should_create_plan()?
    │   ├─ YES → Inject plan tools + orchestration prompt
    │   │         → Agent creates plan via create_plan tool
    │   │         → Agent executes via execute_plan tool
    │   │         → PlanExecutionEngine delegates to AgentPool
    │   └─ NO  → Normal single-agent execution
    │
    ├─ Plugin Hook: pre_tool_call
    │   └─ MultiAgentTriggerHook detects delegation opportunity
    │       → Injects delegation context
    │
    └─ Plugin Hook: post_tool_call
        └─ Detects failure cascade → triggers plan revision
```

---

## Part 4: Design Principles

1. **Opt-in**: Multi-agent and planning are disabled by default. Enable via config or auto-triggered by complexity signals.
2. **Minimal Core Changes**: Leverage existing plugin hooks, DojoExtension protocol, and tool registration — avoid rewriting `AgentLoop`.
3. **Agent as Tool User**: The orchestrator uses `delegate_task` and `create_plan` as regular tools — the LLM decides when to use them based on system prompt instructions.
4. **Shared Memory**: Sub-agents share context through the existing `MemoryManager` + a new `PlanStateProvider`.
5. **Graceful Degradation**: If multi-agent fails, fall back to single-agent mode transparently.
6. **Event-Driven**: Key events (tool failures, quant signals, complexity patterns) trigger mode transitions without user intervention.

---

## Implementation Tasks

### Task 1: Implement `dojoagents/multi_agent/` module

- Create models, pool, orchestrator, tools, triggers
- Register delegation tool in Runtime

### Task 2: Implement `dojoagents/planning/` module  

- Create models, engine, store, tools, triggers
- Register plan tools in Runtime

### Task 3: Integrate with existing `AgentLoop` and `Runtime`

- Add `MultiAgentConfig` and `PlanConfig` to `AgentsConfig`
- Add plan activation check in `AgentLoop.run()`
- Register all new tools in `Runtime.from_config_store()`

### Task 4: Add event-driven trigger hooks

- Register `MultiAgentTriggerHook` in plugin system
- Register `PlanActivationHook` in plugin system
- Add quant workflow auto-plan logic

### Task 5: Testing

- Unit tests for Plan models and execution engine
- Unit tests for AgentPool and delegation
- Integration tests for trigger detection
- End-to-end test: complex quant request → auto-plan → multi-agent execution
