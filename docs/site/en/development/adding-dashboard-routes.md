# Adding Dashboard Routes

Use the existing dashboard layers:

| Content | Location |
| --- | --- |
| Router | `dojoagents/dashboard/routers/` |
| Schemas | `dojoagents/dashboard/schemas/` |
| Business logic | `dojoagents/dashboard/services/` |
| Dependencies | `dojoagents/dashboard/deps.py` |
| App include | `dojoagents/dashboard/server.py` |

Expected HTTP failures should use `fastapi.HTTPException` or the existing `JSONResponse(status_code=..., content={"error": ...})` pattern.

