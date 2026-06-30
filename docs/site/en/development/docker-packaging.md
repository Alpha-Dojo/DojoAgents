# Docker Packaging

The repository ships two image definitions under `docker/`. Build both from the **repository root** with `docker build`.

| Image | Dockerfile | Purpose |
|-------|------------|---------|
| Dashboard runtime | `docker/agent/Dockerfile` | Package and run `dojoagents dashboard` |
| Documentation site | `docker/docs-site/Dockerfile` | Build the MkDocs static site and serve it with nginx |

## Dashboard Runtime Image

### Build stages

`docker/agent/Dockerfile` is a multi-stage build:

1. **frontend**: `npm ci` and `npm run build` on Node 20, producing `dojoagents/dashboard/web/dist/`.
2. **builder**: Copy Python sources and the pre-built frontend, then build a wheel (removes `package.json` first so wheel packaging does not run npm again).
3. **runtime**: Install the wheel on `python:3.12-slim` and start the dashboard by default.

### Build and run

```bash
docker build -f docker/agent/Dockerfile -t dojoagents:latest .
```

```bash
docker run --rm -p 8765:8765 -v dojoagents-data:/root/.dojo dojoagents:latest
```

Open `http://127.0.0.1:8765` in a browser.

### Data and configuration

- Config and data live under `/root/.dojo` in the container (same default as local `~/.dojo`).
- Mount a named volume or bind mount to keep `agents.yaml`, caches, and session data across restarts.
- Inject model API keys and other secrets via config files or environment variables. Do not bake secrets into the image.

### Common overrides

```bash
docker run --rm -p 8765:8765 \
  -v "$(pwd)/agents.yaml:/root/.dojo/agents.yaml:ro" \
  -e OPENAI_API_KEY="..." \
  dojoagents:latest
```

For custom static asset paths or forced frontend rebuilds when iterating on the image locally, use `DOJO_DASHBOARD_STATIC_DIR` and `DOJO_DASHBOARD_REBUILD_FRONTEND`. Behavior matches dashboard startup described in [Local Development](local-development.md).

## Documentation Site Image

### Build stages

`docker/docs-site/Dockerfile` is also multi-stage:

1. **builder**: Install MkDocs Material and the i18n plugin, then `mkdocs build --strict`.
2. **runtime**: Copy the output into `nginx:1.27-alpine` with `try_files` for directory-style URLs.

### Build and run

```bash
docker build -f docker/docs-site/Dockerfile -t dojoagents-docs:latest .
```

```bash
docker run --rm -p 8080:80 dojoagents-docs:latest
```

- Chinese site: `http://127.0.0.1:8080/`
- English site: `http://127.0.0.1:8080/en/`

To preview docs locally without building an image:

```bash
uv run --extra docs mkdocs serve
```

## Relation to Wheel Builds

[Release Build](release-build.md) runs the frontend build on the host and bundles `web/dist/` into the wheel. The Docker agent image compiles the frontend during the image build; the final runtime image does **not** require Node.js.

Use cases differ:

- **wheel**: PyPI or offline Python distribution.
- **agent image**: One-command dashboard deployment.
- **docs-site image**: Standalone documentation hosting without the agent runtime.
