# DojoAgents dashboard runtime image.
# Build from repo root:
#   docker build -f docker/agent/Dockerfile -t dojoagents:latest .
#
# Run:
#   docker run --rm -p 8765:8765 -v dojoagents-data:/root/.dojo dojoagents:latest

FROM node:20-bookworm-slim AS frontend

WORKDIR /src/dojoagents/dashboard/web

COPY dojoagents/dashboard/web/package.json dojoagents/dashboard/web/package-lock.json ./
RUN npm ci

COPY dojoagents/dashboard/web/ ./
RUN npm run build


FROM python:3.12-bookworm AS builder

WORKDIR /src

COPY pyproject.toml README.md ./
COPY dojoagents/ dojoagents/
COPY --from=frontend /src/dojoagents/dashboard/web/dist/ dojoagents/dashboard/web/dist/

# ponytail: dist is pre-built in the node stage; drop package.json so packaging_hooks skip npm
RUN rm -f dojoagents/dashboard/web/package.json dojoagents/dashboard/web/package-lock.json

RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /dist


FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY --from=builder /dist/dojoagents-*.whl /tmp/

RUN pip install --no-cache-dir /tmp/dojoagents-*.whl \
    && rm /tmp/dojoagents-*.whl

CMD ["dojoagents", "dashboard", "--host", "0.0.0.0", "--port", "8765"]
