# Adding Gateway Adapter

## Standard Path

1. Add `dojoagents/gateway/adapters/<platform>.py`.
2. Follow or subclass `BaseGatewayAdapter`.
3. Register the adapter in `dojoagents/gateway/registry.py`.
4. Add config fields and tests.

Adapters normalize platform events, send replies, handle authentication, and keep platform-specific logic out of the agent core.

