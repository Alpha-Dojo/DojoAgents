# Global Logger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a YAML-configured global logger for DojoAgents.

**Architecture:** Extend the existing config dataclasses with `LoggingConfig`, teach `ConfigStore` to read the `logging` YAML section, and add a focused `dojoagents.logging` module that configures the package logger with one managed stream handler.

**Tech Stack:** Python 3.11, standard library `logging`, dataclasses, pytest.

---

### File Structure

- Modify `dojoagents/config/models.py`: add `LoggingConfig` and include it in `AgentsConfig`.
- Modify `dojoagents/config/loader.py`: parse the merged `logging` mapping.
- Create `dojoagents/logging.py`: expose defaults, `configure_logging`, and `get_logger`.
- Modify `tests/test_core_contracts.py`: cover config parsing and logger behavior.

### Task 1: Configuration Model

**Files:**
- Modify: `dojoagents/config/models.py`
- Modify: `dojoagents/config/loader.py`
- Test: `tests/test_core_contracts.py`

- [ ] **Step 1: Write the failing test**

Add assertions that default config includes logging defaults and YAML can override `logging.level`, `logging.format`, and `logging.date_format`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_core_contracts.py::test_config_store_loads_defaults_merges_user_config_expands_env_and_redacts -q`
Expected: FAIL because `AgentsConfig` has no `logging` attribute.

- [ ] **Step 3: Write minimal implementation**

Add `LoggingConfig` and parse `logging_raw` in `_to_config`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_core_contracts.py::test_config_store_loads_defaults_merges_user_config_expands_env_and_redacts -q`
Expected: PASS.

### Task 2: Logger Module

**Files:**
- Create: `dojoagents/logging.py`
- Test: `tests/test_core_contracts.py`

- [ ] **Step 1: Write failing tests**

Add tests for formatted output, no duplicate handlers after repeated configuration, and invalid level raising `ValueError`.

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run python -m pytest tests/test_core_contracts.py -q`
Expected: FAIL because `dojoagents.logging` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `DEFAULT_LOG_FORMAT`, `DEFAULT_DATE_FORMAT`, `configure_logging`, and `get_logger`.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run python -m pytest tests/test_core_contracts.py -q`
Expected: PASS.

### Task 3: Focused Verification

**Files:**
- Verify all modified files.

- [ ] **Step 1: Run core test file**

Run: `uv run python -m pytest tests/test_core_contracts.py -q`
Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `uv run python -m pytest -q`
Expected: PASS.
