# Dashboard Deployment

## Local Deployment

Build the frontend:

```bash
cd dojoagents/dashboard/web
npm install
npm run build
```

Start the backend:

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## Exposure

The default recommendation is binding to `127.0.0.1`. If binding externally, add authentication, access control, and network isolation.

