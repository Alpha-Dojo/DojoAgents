# Design

This section records current technical designs and integration contracts that explain how a specific subsystem must behave.

- [K-line Snapshot Query Ownership](kline-snapshot-queries.md): ownership boundaries between DojoAgents and DojoSDK.
- [Session Design and Integration](session-history.md): runtime session lifecycle and dashboard integration.
- [External SessionStore / BlobStore Adapters](session-store-adapter.md): persistence adapter contract and conformance gate.
- [Async Runtime](async-runtime.md): AnyIO boundaries, TaskGroup ownership, timeouts and cancellation,
  thread and buffer limits, SSE cross-thread bridging, subprocess reclamation, and the asyncio
  compatibility allowlist.
- [Provider Request Boundary](provider-request-boundary.md): internal messages, OpenAI-compatible
  wire policies, and outbound adapter ownership.

System-wide component relationships belong under **Architecture**. Unfinished proposals, migration sequences, and historical decisions belong under **Plans**.
