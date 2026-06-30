# Gateway Architecture

Gateway normalizes chat platform webhook events into DojoAgents requests and sends responses back to platform targets.

## Components

| Component | Purpose |
| --- | --- |
| `gateway/server.py` | Gateway FastAPI app |
| `gateway/runner.py` | Runtime runner |
| `gateway/registry.py` | Adapter registry |
| `gateway/adapters/` | Platform adapters |
| `gateway/state.py` | SQLite session and gateway state |
| `gateway/pairing.py` | Pairing flow |

Adapters should normalize messages, send responses, and handle platform-specific authentication and errors.

