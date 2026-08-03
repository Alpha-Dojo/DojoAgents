# Known Limitations

This register records confirmed, implementation-relevant gaps in the working tree based on `0d3389e`. It separates observable behavior from proposed fixes. Keep entries until a regression test demonstrates the limitation is resolved.

## Status vocabulary

- **Open**: confirmed in code or a reproducible run; no complete fix is present.
- **Mitigated**: a documented workaround or boundary reduces risk, but the root limitation remains.
- **Resolved in working tree**: code and a focused regression test are present locally; the entry can be removed after normal review.

## Open limitations

### DA-KI-001 — No agent-run wall-clock deadline

- **Status:** Open
- **Scope:** `DojoStrandsModelBridge.stream()`, `AgentLoop.run()`
- **Evidence:** the bridge waits on `queue.get()` without a timeout, and model invocations are not wrapped in a run-level `asyncio.wait_for()`. Tool and selected transport operations have their own timeouts, but there is no cumulative deadline for a complete agent run.
- **Impact:** a provider stream that neither completes nor raises can leave a run active indefinitely; iteration limits do not bound elapsed time.
- **Workaround:** use the background-run cancellation endpoint and enforce an ingress or process-level deadline.
- **Follow-up:** add a configurable run deadline, propagate cancellation to the model task, and test a provider that never yields a terminal result.

### DA-KI-002 — Pipeline and harness budgets are not cumulative

- **Status:** Open
- **Scope:** `tasks/runtime_helpers.py::run_agent_with_tasks()`, harness recovery in `AgentLoop.run()`
- **Evidence:** a pipeline may call the agent for up to five steps. Each pipeline step may add up to eight harness-recovery invocations, and every invocation receives the normal per-invocation `Limits`; the code does not maintain a separate cumulative turn or model-call budget for the full pipeline run.
- **Impact:** a non-converging task can consume substantially more model/tool cycles than `agent.max_iterations` alone suggests.
- **Workaround:** keep pipeline step counts and `max_iterations` conservative, and cancel runs that stop making observable progress.
- **Follow-up:** introduce a shared run budget covering pipeline steps, recovery calls, model calls, tool calls and elapsed time; expose the consumed totals in response metadata.

<a id="da-ki-003"></a>

### DA-KI-003 — `max_content_bytes` is not enforced by web extraction

- **Status:** Open
- **Scope:** `WebToolsConfig.max_content_bytes`, `tools/web_searcher.py`
- **Evidence:** the setting is loaded and documented, but the extractor does not consult it while reading HTTP response bodies. Character-based post-processing limits are applied only after content has been received.
- **Impact:** a large response can consume more network bandwidth and memory than the configured byte limit implies.
- **Workaround:** restrict extraction to trusted URLs and enforce response-size limits at an outbound proxy when needed.
- **Follow-up:** stream response bytes, stop at the configured limit, mark truncated results, and add multibyte-content tests.

### DA-KI-004 — Search results do not retain publication timestamps

- **Status:** Open
- **Scope:** `_sanitize_search_rows()`, built-in sector-attribution task
- **Evidence:** the task requires `published_at` validation, while sanitized search rows retain only `title`, `url`, `description` and `position` even if a backend supplied a date.
- **Impact:** the agent cannot establish the required date window from search metadata alone and may accept stale evidence unless it verifies the source content.
- **Workaround:** call `web_extract` for candidate sources and validate the publication date from the extracted page before writing task output.
- **Follow-up:** define a backend-neutral optional `published_at` field, preserve it in adapters and sanitization, and test date-range filtering.

### DA-KI-005 — Dashboard authentication is deployment-owned

- **Status:** Mitigated
- **Scope:** Dashboard HTTP API
- **Evidence:** routes do not perform built-in identity or role checks. The default listener is `127.0.0.1`, and [Dashboard API](../reference/dashboard-api.md#access-control-and-security-boundary) documents the boundary.
- **Impact:** any caller that can reach the listen address can invoke chat and administrative endpoints.
- **Workaround:** keep the service on a trusted local interface or place it behind authenticated ingress with TLS, network policy and auditing.
- **Follow-up:** either add an optional first-party authentication mode or publish a supported authenticated deployment profile.

### DA-KI-011 — Frontend lockfile resolves a vulnerable PostCSS version

- **Status:** Open
- **Scope:** Dashboard frontend build dependencies
- **Evidence:** `npm audit` reports [GHSA-r28c-9q8g-f849](https://github.com/advisories/GHSA-r28c-9q8g-f849) for transitive `postcss@8.5.15`; affected versions are `<=8.5.17` and a fix is available.
- **Impact:** processing an attacker-controlled previous source map during a frontend build may disclose arbitrary `.map` files from the build host. This is a build-time dependency risk, not evidence that the generated Dashboard bundle is directly exploitable in a browser.
- **Workaround:** build only trusted source trees in an isolated CI environment and do not process untrusted CSS/source maps.
- **Follow-up:** update the locked transitive dependency to a fixed PostCSS release, rerun `npm ci`, `npm audit` and `npm run build`, then retain the resulting lockfile change.

## Resolved checks in this working tree

| ID | Status | Correction | Regression coverage |
| --- | --- | --- | --- |
| DA-KI-006 | Resolved in working tree | Explicit `null` now disables a web search or extract backend instead of silently restoring the default. | `tests/test_web_searcher.py` |
| DA-KI-007 | Resolved in working tree | Legacy portfolio data now passes through v2 before conversion to the current candidate/order schema. | `tests/dashboard/stores/test_portfolio_migration.py`, `test_portfolio_orders.py` |
| DA-KI-008 | Resolved in working tree | Bulk kline snapshots are indexed by their `symbol` column, reused, and bypassed for explicit date windows. | `tests/dashboard/test_dojo_data_gateway.py`, `test_kline_single_day_vs_bulk.py` |
| DA-KI-009 | Resolved in working tree | MCP sampling applies the smaller of the provider output limit and the caller's `maxTokens`. | `tests/test_mcp_advanced.py` |
| DA-KI-010 | Resolved in working tree | Turn-intent classification is skipped when no session history exists, avoiding a model call whose result could not affect the prompt. | `tests/test_turn_intent.py`, `test_agent_harness.py` |
