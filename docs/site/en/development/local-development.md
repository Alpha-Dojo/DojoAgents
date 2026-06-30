# Local Development

## Python

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Dashboard Frontend

```bash
cd dojoagents/dashboard/web
npm install
npm run dev
```

Backend:

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

## Documentation

```bash
uv run --extra docs mkdocs serve
```

```bash
uv run --extra docs mkdocs build --strict
```

Temporary scripts must live under `.agents/scripts/`.

