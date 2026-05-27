# DojoAgents vs Hermes-Agent: Plugin Execution Gap Analysis & Action Plan

This document compares the plugin execution hook framework of **Hermes-Agent** and **DojoAgents**, identifies gaps, and outlines the step-by-step execution plan to implement the remaining plugin hooks in DojoAgents.

---

## 1. Architectural Gap Analysis

### 1.1 Hook Locations
* **Hermes-Agent**:
  * Employs hooks at 17 key points of execution (e.g. `on_session_start`, `pre_llm_call`, `pre_api_request`, `post_api_request`, `pre_tool_call`, `post_tool_call`, `transform_tool_result`, `transform_llm_output`, `post_llm_call`, `on_session_end`, etc.).
  * Splices tool-specific hooks (`pre_tool_call`, `post_tool_call`, `transform_tool_result`) inside `model_tools.py` dispatcher.
  * Ensures that exit hooks (`transform_llm_output`, `post_llm_call`, `on_session_end`) run reliably across all code paths.
* **DojoAgents**:
  * Currently has 4 hooks partially integrated in `AgentLoop.run()` (`on_session_start`, `pre_llm_call`, `pre_api_request`, `post_api_request`).
  * Missing tool-level hooks: `pre_tool_call`, `post_tool_call`, `transform_tool_result`.
  * Missing exit hooks: `transform_llm_output`, `post_llm_call`, `on_session_end` across normal exits, iteration limit exits, and exception exits.

### 1.2 Hook Arguments & Vetoing Contracts
* **Vetoing / Blocking**: Hermes allows `pre_tool_call` to return `{"action": "block", "message": "reason"}`. If blocked, the tool execution is bypassed and a failed JSON response is returned to the LLM.
* **Result Rewriting**: Hermes allows `transform_tool_result` to return a string to rewrite a tool's execution result, and `transform_llm_output` to rewrite the final LLM message.
* **Exception Safety**: Both frameworks implement exception wrapping around hook calls to prevent custom plugin callbacks from crashing the core agent loop.

---

## 2. Detailed Execution Plan

### Step 1: Update Test Coverage (`tests/test_agent_loop_plugins.py`)
Add comprehensive test cases to verify:
1. `pre_tool_call` blocking returns a failed `ToolResult` without running the tool executor.
2. `post_tool_call` receives tool arguments, results, and duration.
3. `transform_tool_result` rewrites a tool's successful or failed result.
4. `transform_llm_output` modifies the final response content.
5. `post_llm_call` receives the user message and final response content.
6. `on_session_end` fires with `completed=True` on success and `completed=False` on errors/iteration limits.

### Step 2: Implement Tool & Exit Hooks in `dojoagents/agent/loop.py`
1. **Tool Blocking & Vetoing**:
   Inside the `tool_calls` loop, call the `pre_tool_call` hook. If any hook returns `{"action": "block"}`, bypass the tool and add a failed `ToolResult` with the block message.
2. **Tool Timing & Post-Execution Hooks**:
   Track total execution duration using `time.monotonic()`. For each executed tool, fire `post_tool_call` and `transform_tool_result` to allow plugins to audit or rewrite output.
3. **Exit Hooks Integration**:
   Define a helper method `_run_exit_hooks` inside `AgentLoop` to execute `transform_llm_output`, `post_llm_call`, and `on_session_end` uniformly. Call this helper on:
   - Normal completion (no tool calls generated).
   - Guardrail halt exits.
   - Exception caught exits.
   - Iteration limit reached exits.
