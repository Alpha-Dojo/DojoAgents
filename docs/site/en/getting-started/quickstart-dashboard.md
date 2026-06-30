# Start Dashboard

## Start the Backend

After installing dependencies and building the frontend, run:

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765/
```

## Frontend Hot Reload

Start the backend first, then run Vite:

```bash
cd dojoagents/dashboard/web
npm run dev
```

Open:

```text
http://localhost:5173/
```

## Mock Data

```bash
cd dojoagents/dashboard/web
VITE_USE_MOCKS=true npm run dev
```

