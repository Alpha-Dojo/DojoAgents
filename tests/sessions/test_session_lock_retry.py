"""Regression: portalocker AlreadyLocked must not kill agent runs as Errno 35."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import portalocker
import pytest

from dojoagents.sessions.stores.file import FileSessionStore


def test_transaction_retries_when_session_lock_is_busy(tmp_path: Path) -> None:
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret")
    store.root.mkdir(parents=True, exist_ok=True)
    held = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with portalocker.Lock(str(store._lock_path), mode="a+", timeout=30):
            held.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold_lock, daemon=True)
    holder.start()
    assert held.wait(timeout=2)

    started = time.perf_counter()

    def work(state: dict) -> str:
        return "ok"

    # Release shortly after the waiter begins retrying.
    def delayed_release() -> None:
        time.sleep(0.3)
        release.set()

    threading.Thread(target=delayed_release, daemon=True).start()
    result = store._transaction_sync(False, work)
    elapsed = time.perf_counter() - started

    assert result == "ok"
    assert elapsed >= 0.25
    release.set()
    holder.join(timeout=2)
