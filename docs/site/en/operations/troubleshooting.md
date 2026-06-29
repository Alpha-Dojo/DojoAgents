# Troubleshooting

## Dashboard Does Not Open

Check frontend build:

```bash
cd dojoagents/dashboard/web
npm run build
```

Check backend:

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## Model Request Fails

Check provider, base URL, model, API key, and `dojoagents model`.

## Gateway Does Not Receive Messages

Check adapter config, webhook reachability, and pairing status.

## SSE Disconnects

Check `stream=true`, proxy buffering, and backend logs.

