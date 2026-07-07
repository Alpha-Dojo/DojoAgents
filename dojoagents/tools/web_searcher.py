from __future__ import annotations

import html
import ipaddress
import json
import re
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qsl, urlparse

import httpx

from dojoagents.config.models import WebToolsConfig
from dojoagents.tools.registry import ToolSpec

_SECRET_KEYS = {"api_key", "apikey", "token", "secret", "password", "sig", "signature"}
_BASE64_IMAGE_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
SearchBackendAdapter = Callable[[str, int, WebToolsConfig], Awaitable[list[dict[str, Any]]]]
ExtractBackendAdapter = Callable[[list[str], WebToolsConfig], Awaitable[list[dict[str, Any]]]]

_SEARCH_BACKENDS: dict[str, SearchBackendAdapter] = {}
_EXTRACT_BACKENDS: dict[str, ExtractBackendAdapter] = {}
_HTML_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DDGS_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
    r'(?:<a[^>]*class="result__snippet"[^>]*>(?P<snippet_a>.*?)</a>|'
    r'<div[^>]*class="result__snippet"[^>]*>(?P<snippet_div>.*?)</div>)?',
    re.IGNORECASE | re.DOTALL,
)


def _normalize_urls(args: dict[str, Any], *, max_urls: int) -> list[str]:
    raw_urls = args.get("urls")
    if raw_urls is None and args.get("url"):
        raw_urls = [args["url"]]
    if isinstance(raw_urls, str):
        urls = [raw_urls]
    else:
        urls = [str(item).strip() for item in list(raw_urls or [])]
    urls = [url for url in urls if url]
    if not urls:
        raise RuntimeError("web_extract requires at least one URL")
    if len(urls) > max_urls:
        raise RuntimeError(f"web_extract accepts at most {max_urls} URLs per call")
    return urls


def _assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"Blocked URL: unsupported scheme for {url}")
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        raise RuntimeError(f"Blocked URL: private host for {url}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
        raise RuntimeError(f"Blocked URL: private address for {url}")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if key.strip().lower() in _SECRET_KEYS:
            raise RuntimeError(f"Blocked URL: secret-like query parameter in {url}")


def _sanitize_search_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        sanitized.append(
            {
                "title": str(row.get("title") or ""),
                "url": str(row.get("url") or ""),
                "description": str(row.get("description") or row.get("snippet") or ""),
                "position": int(row.get("position") or index),
            }
        )
    return sanitized


def _trim_content(text: str, cfg: WebToolsConfig) -> tuple[str, bool, str]:
    cleaned = _BASE64_IMAGE_RE.sub("[image omitted]", text)
    if len(cleaned) <= cfg.summary_threshold_chars:
        return cleaned, False, "none"
    clipped = cleaned[: cfg.max_summary_chars].rstrip()
    return clipped + "\n...[truncated]", True, "truncate"


def _default_user_agent() -> str:
    try:
        pkg_version = version("dojoagents")
    except PackageNotFoundError:
        pkg_version = "0.0.0"
    return f"DojoAgents/{pkg_version} (+https://github.com/Alpha-Dojo/DojoAgents)"


def _resolve_user_agent(cfg: WebToolsConfig) -> str:
    custom = (cfg.user_agent or "").strip()
    if custom:
        return custom
    return _default_user_agent()


def _make_async_client(cfg: WebToolsConfig, **kwargs: Any) -> httpx.AsyncClient:
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("User-Agent", _resolve_user_agent(cfg))
    return httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers, **kwargs)


def _resolve_search_base_url(cfg: WebToolsConfig) -> str:
    return (cfg.search_base_url or "https://html.duckduckgo.com").rstrip("/")


def _strip_html_to_text(raw: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.IGNORECASE | re.DOTALL)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else ""
    without_scripts = _HTML_SCRIPT_RE.sub(" ", raw)
    text = _HTML_TAG_RE.sub(" ", without_scripts)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return title, text


async def _search_backend_request(
    backend: str,
    query: str,
    limit: int,
    cfg: WebToolsConfig,
) -> list[dict[str, Any]]:
    adapter = _SEARCH_BACKENDS.get(backend)
    if adapter is None:
        raise RuntimeError(f"Web search backend '{backend}' is not available")
    return await adapter(query, limit, cfg)


async def _extract_backend_request(
    backend: str,
    urls: list[str],
    cfg: WebToolsConfig,
) -> list[dict[str, Any]]:
    adapter = _EXTRACT_BACKENDS.get(backend)
    if adapter is None:
        raise RuntimeError(f"Web extract backend '{backend}' is not available")
    return await adapter(urls, cfg)


def register_search_backend(name: str, adapter: SearchBackendAdapter) -> None:
    _SEARCH_BACKENDS[name] = adapter


def register_extract_backend(name: str, adapter: ExtractBackendAdapter) -> None:
    _EXTRACT_BACKENDS[name] = adapter


def _html_fragment_to_text(raw: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", raw))).strip()


async def _ddgs_search_adapter(
    query: str,
    limit: int,
    cfg: WebToolsConfig,
) -> list[dict[str, Any]]:
    async with _make_async_client(cfg) as client:
        response = await client.get(
            f"{_resolve_search_base_url(cfg)}/html/",
            params={"q": query},
        )
        response.raise_for_status()
        raw_html = response.text
    rows: list[dict[str, Any]] = []
    for index, match in enumerate(_DDGS_RESULT_RE.finditer(raw_html), start=1):
        if index > limit:
            break
        snippet = match.group("snippet_a") or match.group("snippet_div") or ""
        rows.append(
            {
                "title": _html_fragment_to_text(match.group("title")),
                "url": html.unescape(match.group("url")),
                "description": _html_fragment_to_text(snippet),
                "position": index,
            }
        )
    return rows


register_search_backend("ddgs", _ddgs_search_adapter)


async def _fetch_extract_adapter(
    urls: list[str],
    cfg: WebToolsConfig,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    async with _make_async_client(cfg) as client:
        for url in urls:
            try:
                response = await client.get(url)
                response.raise_for_status()
                title, content = _strip_html_to_text(response.text)
                results.append(
                    {
                        "url": url,
                        "title": title,
                        "content": content,
                        "error": None,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "url": url,
                        "title": "",
                        "content": "",
                        "error": str(e),
                    }
                )
    return results


register_extract_backend("fetch", _fetch_extract_adapter)


def get_web_searcher_specs(cfg: WebToolsConfig) -> list[ToolSpec]:
    async def web_search(args: dict[str, Any]) -> dict[str, Any]:
        backend = cfg.search_backend
        if not backend:
            raise RuntimeError("web_search backend is not configured")
        query = str(args.get("query") or "").strip()
        if not query:
            raise RuntimeError("web_search requires a non-empty query")
        limit = int(args.get("limit") or 5)
        rows = await _search_backend_request(backend, query, limit, cfg)
        payload = {"success": True, "query": query, "web": _sanitize_search_rows(rows)}
        return {
            "content": json.dumps(payload, ensure_ascii=False),
            "data": payload,
            "metadata": {"backend": backend, "processing_applied": "metadata_only"},
        }

    async def web_extract(args: dict[str, Any]) -> dict[str, Any]:
        backend = cfg.extract_backend
        if not backend:
            raise RuntimeError("web_extract backend is not configured")
        urls = _normalize_urls(args, max_urls=cfg.max_extract_urls)
        for url in urls:
            _assert_safe_url(url)
        rows = await _extract_backend_request(backend, urls, cfg)
        truncated = False
        processing_applied = "none"
        results: list[dict[str, Any]] = []
        for row in rows:
            content = str(row.get("content") or "")
            trimmed, was_truncated, applied = _trim_content(content, cfg)
            truncated = truncated or was_truncated
            if applied != "none":
                processing_applied = applied
            results.append(
                {
                    "url": str(row.get("url") or ""),
                    "title": str(row.get("title") or ""),
                    "content": trimmed,
                    "error": row.get("error"),
                }
            )
        payload = {"success": True, "results": results}
        return {
            "content": json.dumps(payload, ensure_ascii=False),
            "data": payload,
            "truncated": truncated,
            "metadata": {"backend": backend, "processing_applied": processing_applied},
        }

    return [
        ToolSpec(
            name="web_search",
            description=(
                "Search the web and return metadata rows only. Use event/entity/topic keywords; "
                "do not add a year unless the user specified one. Use web_extract when full page "
                "content is needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
            handler=web_search,
        ),
        ToolSpec(
            name="web_extract",
            description="Fetch and normalize page content for one or more public URLs after search.",
            parameters={
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "url": {"type": "string"},
                },
            },
            handler=web_extract,
        ),
    ]
