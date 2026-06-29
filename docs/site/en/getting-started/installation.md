# Installation

## Requirements

- Python `>=3.11`
- Node.js `>=18`
- npm `>=9`

## Install from Source

From the repository root:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Runtime-only dependencies:

```bash
uv pip install -r requirements.txt
```

## Build the Dashboard Frontend

```bash
cd dojoagents/dashboard/web
npm install
npm run build
```

## Verify

```bash
dojoagents --help
```

Development invocation:

```bash
uv run --extra dev dojoagents --help
```

