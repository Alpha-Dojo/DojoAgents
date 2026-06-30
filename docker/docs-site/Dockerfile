# DojoAgents MkDocs static site image.
# Build from repo root:
#   docker build -f docker/docs-site/Dockerfile -t dojoagents-docs:latest .
#
# Run:
#   docker run --rm -p 8080:80 dojoagents-docs:latest
#
# Chinese site: http://127.0.0.1:8080/
# English site: http://127.0.0.1:8080/en/

FROM python:3.12-slim AS builder

WORKDIR /src

COPY mkdocs.yml pyproject.toml README.md ./
COPY docs/site/ docs/site/

RUN pip install --no-cache-dir \
        "mkdocs-material>=9,<10" \
        "mkdocs-static-i18n>=1,<2" \
    && mkdocs build --strict --site-dir /site


FROM nginx:1.27-alpine AS runtime

COPY --from=builder /site /usr/share/nginx/html

RUN printf '%s\n' \
    'server {' \
    '    listen 80;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '' \
    '    location / {' \
    '        try_files $uri $uri/ $uri/index.html =404;' \
    '    }' \
    '}' \
    > /etc/nginx/conf.d/default.conf

CMD ["nginx", "-g", "daemon off;"]
