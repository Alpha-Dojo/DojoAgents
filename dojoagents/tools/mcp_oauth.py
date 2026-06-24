from dojoagents.logging import LOGGER
import asyncio
import json
import logging
import os
import re
import secrets
import socket
import stat
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("dojoagents")

_OAUTH_AVAILABLE = False
try:
    from mcp.client.auth import OAuthClientProvider
    from mcp.shared.auth import (
        OAuthClientInformationFull,
        OAuthClientMetadata,
        OAuthMetadata,
        OAuthToken,
    )

    _OAUTH_AVAILABLE = True
except ImportError:
    pass

try:
    from pydantic import AnyUrl
except ImportError:
    AnyUrl = None


class OAuthNonInteractiveError(RuntimeError):
    pass


_oauth_port: int | None = None


def _get_token_dir() -> Path:
    base = Path.home() / ".dojo"
    return base / "mcp-tokens"


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name).strip("_")[:128] or "default"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _is_interactive() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _can_open_browser() -> bool:
    if os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"):
        return False
    if os.name == "nt":
        return True
    try:
        if os.uname().sysname == "Darwin":
            return True
    except AttributeError:
        pass
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to read {path}: {exc}")
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}.{secrets.token_hex(4)}")
    try:
        fd = os.open(
            str(tmp),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class DojoTokenStorage:
    def __init__(self, server_name: str):
        self._server_name = _safe_filename(server_name)

    def _tokens_path(self) -> Path:
        return _get_token_dir() / f"{self._server_name}.json"

    def _client_info_path(self) -> Path:
        return _get_token_dir() / f"{self._server_name}.client.json"

    def _meta_path(self) -> Path:
        return _get_token_dir() / f"{self._server_name}.meta.json"

    async def get_tokens(self) -> Optional[Any]:
        data = _read_json(self._tokens_path())
        if data is None:
            return None
        absolute_expiry = data.pop("expires_at", None)
        if absolute_expiry is not None:
            data["expires_in"] = int(max(absolute_expiry - time.time(), 0))
        try:
            return OAuthToken.model_validate(data)
        except Exception as exc:
            logger.warning(f"Corrupt tokens at {self._tokens_path()} -- ignoring: {exc}")
            return None

    async def set_tokens(self, tokens: Any) -> None:
        payload = tokens.model_dump(mode="json", exclude_none=True)
        expires_in = payload.get("expires_in")
        if expires_in is not None:
            try:
                payload["expires_at"] = time.time() + int(expires_in)
            except (TypeError, ValueError):
                pass
        _write_json(self._tokens_path(), payload)

    async def get_client_info(self) -> Optional[Any]:
        data = _read_json(self._client_info_path())
        if data is None:
            return None
        try:
            return OAuthClientInformationFull.model_validate(data)
        except Exception as exc:
            logger.warning(f"Corrupt client info at {self._client_info_path()} -- ignoring: {exc}")
            return None

    async def set_client_info(self, client_info: Any) -> None:
        _write_json(self._client_info_path(), client_info.model_dump(mode="json", exclude_none=True))

    def save_oauth_metadata(self, metadata: Any) -> None:
        _write_json(self._meta_path(), metadata.model_dump(exclude_none=True, mode="json"))

    def load_oauth_metadata(self) -> Optional[Any]:
        data = _read_json(self._meta_path())
        if data is None:
            return None
        try:
            return OAuthMetadata.model_validate(data)
        except Exception as exc:
            logger.warning(f"Corrupt OAuth metadata at {self._meta_path()} -- ignoring: {exc}")
            return None

    def remove(self) -> None:
        for p in (self._tokens_path(), self._client_info_path(), self._meta_path()):
            p.unlink(missing_ok=True)

    def has_cached_tokens(self) -> bool:
        return self._tokens_path().exists()


def _make_callback_handler() -> tuple[type, dict]:
    result: dict[str, Any] = {"auth_code": None, "state": None, "error": None}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            params = parse_qs(urlparse(self.path).query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            error = params.get("error", [None])[0]

            result["auth_code"] = code
            result["state"] = state
            result["error"] = error

            body = (
                ("<html><body><h2>Authorization Successful</h2>" "<p>You can close this tab and return to DojoAgents.</p></body></html>")
                if code
                else ("<html><body><h2>Authorization Failed</h2>" f"<p>Error: {error or 'unknown'}</p></body></html>")
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

    return _Handler, result


async def _redirect_handler(authorization_url: str) -> None:
    msg = f"\n  MCP OAuth: authorization required.\n" f"  Open this URL in your browser:\n\n" f"    {authorization_url}\n"
    LOGGER.info(msg, file=sys.stderr)

    if _can_open_browser():
        try:
            webbrowser.open(authorization_url)
        except Exception:
            pass


async def _wait_for_callback() -> tuple[str, Optional[str]]:
    if _oauth_port is None:
        raise RuntimeError("OAuth callback port not set")

    handler_cls, result = _make_callback_handler()

    try:
        server = HTTPServer(("127.0.0.1", _oauth_port), handler_cls)
    except OSError:
        raise OAuthNonInteractiveError("OAuth callback timed out — could not bind callback port.")

    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    timeout = 300.0
    poll_interval = 0.5
    elapsed = 0.0
    try:
        while elapsed < timeout:
            if result["auth_code"] is not None or result["error"] is not None:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
    finally:
        server.server_close()

    if result["error"]:
        raise RuntimeError(f"OAuth authorization failed: {result['error']}")
    if result["auth_code"] is None:
        raise OAuthNonInteractiveError("OAuth callback timed out")

    return result["auth_code"], result["state"]


def build_oauth_auth(
    server_name: str,
    server_url: str,
    oauth_config: dict | None = None,
) -> Optional[Any]:
    if not _OAUTH_AVAILABLE:
        return None

    cfg = dict(oauth_config or {})
    storage = DojoTokenStorage(server_name)

    requested = int(cfg.get("redirect_port", 0))
    global _oauth_port
    _oauth_port = _find_free_port() if requested == 0 else requested

    client_name = cfg.get("client_name", "DojoAgents")
    scope = cfg.get("scope")
    redirect_uri = f"http://127.0.0.1:{_oauth_port}/callback"

    metadata_kwargs: dict[str, Any] = {
        "client_name": client_name,
        "redirect_uris": [AnyUrl(redirect_uri)] if AnyUrl else [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if scope:
        metadata_kwargs["scope"] = scope
    if cfg.get("client_secret"):
        metadata_kwargs["token_endpoint_auth_method"] = "client_secret_post"

    client_metadata = OAuthClientMetadata.model_validate(metadata_kwargs)

    client_id = cfg.get("client_id")
    if client_id:
        info_dict: dict[str, Any] = {
            "client_id": client_id,
            "redirect_uris": [redirect_uri],
            "grant_types": client_metadata.grant_types,
            "response_types": client_metadata.response_types,
            "token_endpoint_auth_method": client_metadata.token_endpoint_auth_method,
        }
        if cfg.get("client_secret"):
            info_dict["client_secret"] = cfg["client_secret"]
        if cfg.get("client_name"):
            info_dict["client_name"] = cfg["client_name"]
        if cfg.get("scope"):
            info_dict["scope"] = cfg["scope"]
        client_info = OAuthClientInformationFull.model_validate(info_dict)
        _write_json(storage._client_info_path(), client_info.model_dump(mode="json", exclude_none=True))

    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=_redirect_handler,
        callback_handler=_wait_for_callback,
        timeout=float(cfg.get("timeout", 300)),
    )
