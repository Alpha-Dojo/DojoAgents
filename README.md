# DojoAgents

DojoAgents is a quantitative finance agent runtime with a FastAPI/React
dashboard for local analysis workflows.

## Dashboard Quick Start

### Prerequisites

- Python `>=3.11`
- Node.js `>=18`
- npm `>=9`

### Install DojoAgents

From the repository root:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

If you only need runtime dependencies without installing the local package:

```bash
uv pip install -r requirements.txt
```

### Build Dashboard Frontend

```bash
cd dojoagents/dashboard/web
npm install
npm run build
```

The build output is served by the FastAPI dashboard backend.

### Start Dashboard

```bash
dojoagents dashboard --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765/
```

Additional documentation lives under `docs/`.
