from __future__ import annotations

import asyncio
import copy
import importlib
import inspect
import os
from pathlib import Path
from typing import Any

from dojoagents.config.models import StoreProviderConfig
from dojoagents.logging import LOGGER
from dojoagents.sessions.blob_store import BlobStore
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.errors import SessionStoreUnavailableError
from dojoagents.sessions.store import SessionStore
from dojoagents.sessions.stores.file import FileSessionStore


def _load_factory(path: str):
    if ":" not in path:
        raise ValueError("store factory must use module:attribute syntax")
    module_name, attribute = path.split(":", 1)
    if not module_name or not attribute:
        raise ValueError("store factory must use module:attribute syntax")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute)
    if not callable(factory):
        raise TypeError(f"configured store factory {path!r} is not callable")
    return factory


async def _call_factory(path: str, options: dict[str, Any]):
    result = _load_factory(path)(copy.deepcopy(options))
    if inspect.isawaitable(result):
        result = await result
    return result


def _persistent_cursor_secret(root: Path) -> bytes:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".cursor-secret"
    try:
        return path.read_bytes()
    except FileNotFoundError:
        secret = os.urandom(32)
        try:
            with path.open("xb") as handle:
                handle.write(secret)
                handle.flush()
                os.fsync(handle.fileno())
            path.chmod(0o600)
            return secret
        except FileExistsError:
            return path.read_bytes()


async def _verify_started(store, *, kind: str, provider: str):
    try:
        await store.startup()
        health = await store.health()
        if not health.healthy:
            raise SessionStoreUnavailableError(f"{kind} provider {provider!r} is unhealthy")
        return store
    except Exception:
        try:
            await store.shutdown()
        except Exception:
            LOGGER.exception("Failed to shut down unhealthy %s provider %s", kind, provider)
        raise


async def create_session_store(config: StoreProviderConfig) -> SessionStore:
    options = copy.deepcopy(config.options)
    if config.provider == "file":
        root = Path(str(options.get("root") or "~/.dojo/agents/strands_sessions")).expanduser().resolve()
        configured_secret = options.get("cursor_secret")
        if configured_secret is None:
            secret = await asyncio.to_thread(_persistent_cursor_secret, root)
        else:
            secret = str(configured_secret).encode("utf-8")
        store: Any = FileSessionStore(
            root,
            cursor_secret=secret,
            context_usage_history_limit=int(options.get("context_usage_history_limit") or 1000),
        )
    else:
        if not config.factory:
            raise ValueError(f"session store provider {config.provider!r} requires an explicit factory")
        store = await _call_factory(config.factory, options)
    if not isinstance(store, SessionStore):
        raise TypeError(f"session store factory for provider {config.provider!r} returned an incompatible object")
    return await _verify_started(store, kind="session store", provider=config.provider)


async def create_blob_store(config: StoreProviderConfig) -> BlobStore:
    options = copy.deepcopy(config.options)
    if config.provider == "file":
        root = Path(str(options.get("root") or "~/.dojo/agents/session_blobs")).expanduser().resolve()
        store: Any = FileBlobStore(root)
    else:
        if not config.factory:
            raise ValueError(f"blob store provider {config.provider!r} requires an explicit factory")
        store = await _call_factory(config.factory, options)
    if not isinstance(store, BlobStore):
        raise TypeError(f"blob store factory for provider {config.provider!r} returned an incompatible object")
    return await _verify_started(store, kind="blob store", provider=config.provider)


async def shutdown_stores(*stores: Any) -> None:
    for store in stores:
        try:
            await store.shutdown()
        except Exception:
            LOGGER.exception("Failed to shut down store %s", type(store).__name__)
