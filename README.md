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

### Development Run

For active development, you can run the CLI entry point directly without installing the package globally:

Using `uv run`:
```bash
uv run dojoagents/cli/main.py dashboard --host 127.0.0.1 --port 8765
```

Or using `python`:
```bash
python dojoagents/cli/main.py dashboard --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765/
```

## Build Wheel Package

### Prerequisites

- Python `>=3.11`
- Node.js `>=18` and npm `>=9` (required only when building the wheel from source)

### Build

From the repository root:

```bash
uv build
```

Or with the standard Python build frontend:

```bash
python -m pip install build
python -m build
```

The build process automatically:

1. Runs `npm install && npm run build` under `dojoagents/dashboard/web`
2. Removes `node_modules` after a successful frontend build
3. Bundles the resulting `web/dist/` directory into the wheel

Built artifacts are written to the repository-level `dist/` directory:

- `dojoagents-<version>-py3-none-any.whl` — installable wheel (includes pre-built dashboard frontend)
- `dojoagents-<version>.tar.gz` — source distribution

### Install from Wheel

End users installing a pre-built wheel do not need Node.js:

```bash
uv pip install dist/dojoagents-0.0.1-py3-none-any.whl
```

Or:

```bash
pip install dist/dojoagents-0.0.1-py3-none-any.whl
```

Additional documentation lives under `docs/`.



