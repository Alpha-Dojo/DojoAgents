from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "dojoagents"

PERMANENT_ASYNCIO_ALLOWLIST = {
    # AF_UNIX stream helpers that asyncio exposes and AnyIO does not.
    "dojoagents/tools/af_unix_asyncio_compat.py",
    # Fire-and-forget tasks: AnyIO has no detached-task primitive, so background
    # process monitoring keeps one audited escape hatch here.
    "dojoagents/utils/detached_tasks.py",
}

# Migration ratchet: no new production file may import asyncio.  Remove an entry
# in the same change that migrates its final asyncio dependency.  S7 emptied this
# set: the cross-thread bridges in the Dashboard run manager, the Dashboard app
# container, and the MCP tool runtime are now owned BlockingPortals.
TEMPORARY_ASYNCIO_ALLOWLIST: set[str] = set()


def _imports_asyncio(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "asyncio" or alias.name.startswith("asyncio.") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "asyncio" or (node.module and node.module.startswith("asyncio.")):
                return True
    return False


def _production_asyncio_files() -> set[str]:
    return {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in PACKAGE_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and _imports_asyncio(path)
    }


def test_asyncio_imports_are_confined_to_registered_boundaries() -> None:
    actual = _production_asyncio_files()
    allowed = PERMANENT_ASYNCIO_ALLOWLIST | TEMPORARY_ASYNCIO_ALLOWLIST

    unexpected = actual - allowed
    stale = TEMPORARY_ASYNCIO_ALLOWLIST - actual

    assert not unexpected, (
        "New production files imported asyncio without a registered migration boundary: "
        f"{sorted(unexpected)}"
    )
    assert not stale, (
        "Remove migrated files from TEMPORARY_ASYNCIO_ALLOWLIST: "
        f"{sorted(stale)}"
    )


def test_memory_object_streams_have_explicit_finite_buffers() -> None:
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func.value if isinstance(node.func, ast.Subscript) else node.func
            if not isinstance(target, ast.Attribute) or target.attr != "create_memory_object_stream":
                continue
            keyword = next((item.value for item in node.keywords if item.arg == "max_buffer_size"), None)
            capacity = node.args[0] if node.args else keyword
            rendered = ast.unparse(capacity) if capacity is not None else ""
            if capacity is None or rendered in {"math.inf", "float('inf')", 'float("inf")'}:
                relative = path.relative_to(REPOSITORY_ROOT).as_posix()
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, (
        "Memory object streams must declare a finite max_buffer_size: "
        f"{violations}"
    )


def test_direct_anyio_thread_offloads_are_confined_to_async_runtime() -> None:
    allowed = {"dojoagents/utils/async_runtime.py"}
    violations: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(REPOSITORY_ROOT).as_posix()
        if relative in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            if not isinstance(target, ast.Attribute) or target.attr != "run_sync":
                continue
            to_thread = target.value
            if not isinstance(to_thread, ast.Attribute) or to_thread.attr != "to_thread":
                continue
            if isinstance(to_thread.value, ast.Name) and to_thread.value.id == "anyio":
                violations.append(f"{relative}:{node.lineno}")
    assert not violations, (
        "Direct anyio.to_thread.run_sync calls must use run_sync_bounded() or "
        f"ThreadedBlockingPortal.run_sync(): {violations}"
    )


def test_permanent_allowlist_contains_only_compatibility_adapters() -> None:
    assert PERMANENT_ASYNCIO_ALLOWLIST == {
        "dojoagents/tools/af_unix_asyncio_compat.py",
        "dojoagents/utils/detached_tasks.py",
    }
