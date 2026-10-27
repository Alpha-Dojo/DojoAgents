# External SessionStore / BlobStore Adapter Contract

DojoAgents Core does not depend on MySQL, PostgreSQL, or object-storage drivers. Online deployments inject adapters through `sessions.store.factory` and `sessions.blob_store.factory`. A factory is addressed as `module:attribute`, receives an isolated copy of its options, and returns an object satisfying the `SessionStore` or `BlobStore` protocol.

## Lifecycle and error boundaries

- `startup()`, `health()`, and `shutdown()` must be asynchronous and safe to call repeatedly. A failed startup must release any connection pool it created.
- `health()` performs only a bounded, lightweight query and returns `StoreHealth`. It must not expose a DSN, password, token, or endpoint credential.
- Each write uses a short transaction. A database transaction must never remain open across an LLM call, network tool call, or SSE connection.
- Map both “not found” and “not authorized” to `SessionNotFoundError` so public IDs cannot be used to probe another user's data.
- Map optimistic-version conflicts, lease conflicts, and fencing-token failures to `SessionConflictError`.

## SQL data and index semantics

Every session, message, turn, run, event, usage, checkpoint, object, and lease query must include the `(tenant_id, user_id)` scope. Querying only by a public `session_id`, `run_id`, or `object_id` is not a compliant implementation.

At minimum, enforce these uniqueness constraints (deployments may choose their own table names):

- session: `(tenant_id, user_id, session_id)`; internal `session_uid` is globally unique;
- run: `(session_uid, idempotency_key)` and the owner-scoped `run_id`;
- event: `(run_uid, sequence)`; a non-empty idempotency key is also unique;
- message: `(session_uid, agent_id, sequence)`; turn: `(session_uid, sequence)`;
- usage: `(run_uid, idempotency_key)`; checkpoint: `(session_uid, namespace, key)`;
- object/blob links preserve owner scope, state, and version, and make pending/committed/deleted transitions retryable.

Lease acquisition, renewal, release, and takeover use conditional updates that validate version, lease ID, holder, expiry, and fencing token. A stale worker's fencing token must never be able to commit a new event or turn.

Schema changes use explicit, auditable, reversible migration versions. Application requests must not mutate the production schema implicitly. Production connections use TLS, least-privilege credentials, connection and query timeouts, and capacity-limited pools.

## External conformance gate

After an adapter project installs its own drivers, set:

```bash
export DOJO_TEST_SESSION_STORE_FACTORY='project.adapters.mysql:create_session_store'
export DOJO_TEST_SESSION_STORE_OPTIONS='{"dsn_env":"TEST_MYSQL_DSN","namespace":"ci-run-123"}'
export DOJO_TEST_BLOB_STORE_FACTORY='project.adapters.s3:create_blob_store'
export DOJO_TEST_BLOB_STORE_OPTIONS='{"bucket":"disposable-ci","prefix":"ci-run-123"}'
uv run --extra dev python -m pytest tests/sessions/test_external_store_contract.py -q
```

When these environment variables are present, no contract capability may be skipped. CI uses a disposable schema or bucket prefix. Factories read credentials from a secret manager or named environment variable; options and test output must never contain plaintext secrets.

## File to SQL / object-storage migration rehearsal

Validate the migration in a disposable environment:

1. Dry-run the file-store export and record counts for sessions, messages, turns, runs, events, and objects, plus blob SHA-256 values.
2. Import it twice and confirm idempotency keys and unique indexes prevent count growth.
3. Compare per-scope counts, event sequences, checkpoint versions, object sizes, and blob checksums.
4. Request the same session, run, and object IDs as another user or tenant; every read must return not found.
5. Export again from SQL and compare normalized JSON with the original export.
6. Simulate lease expiry and takeover; confirm the fencing token increases and the stale worker is rejected.
7. Simulate failure after blob put but before DB commit, and after DB reserve but before blob put; verify compensation removes pending data.
8. Complete backup and rollback rehearsals before shifting read traffic, then monitor conflict rate, pool health, latency, and orphan blobs.

Core file-store tests never require SQL drivers. Only the target deployment's conformance gate installs and validates its adapters.
