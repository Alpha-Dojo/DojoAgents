from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class FileStoreError(RuntimeError):
    pass


class CorruptStoreError(FileStoreError):
    pass


class SchemaVersionError(FileStoreError):
    pass


class InvalidStoreKeyError(FileStoreError):
    pass


def _safe_key_path(root: Path, key: str, suffix: str) -> Path:
    candidate = Path(key)
    if not key.strip() or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise InvalidStoreKeyError(f"invalid store key: {key!r}")
    path = root.joinpath(*candidate.parts)
    return path.with_name(f"{path.name}{suffix}")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
        # ===== 只在 Linux/Unix 上执行目录 fsync =====
        # Windows 执行 os.open(path.parent, os.O_RDONLY) 会抛出 PermissionError
        if os.name == "posix":  # Linux / macOS / Unix
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                # 如果目录 fsync 失败，忽略（不影响主流程）
                pass

    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
        if os.name == "posix":
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


class AtomicJsonStore:
    suffix = ".json"

    def __init__(self, root: Path, *, schema_version: int) -> None:
        self.root = root.resolve()
        self.schema_version = schema_version
        self._locks: dict[str, asyncio.Lock] = {}

    def path_for(self, key: str) -> Path:
        return _safe_key_path(self.root, key, self.suffix)

    def _serialize(self, data: Any) -> str:
        return (
            json.dumps(
                {"schema_version": self.schema_version, "data": data},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )

    def _deserialize(self, text: str, key: str) -> Any:
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CorruptStoreError(f"{key}: invalid JSON") from exc
        if not isinstance(document, dict) or "schema_version" not in document:
            raise CorruptStoreError(f"{key}: missing versioned document envelope")
        actual = document.get("schema_version")
        if actual != self.schema_version:
            raise SchemaVersionError(f"{key}: expected {self.schema_version}, got {actual}")
        if "data" not in document:
            raise CorruptStoreError(f"{key}: missing data field")
        return document["data"]

    async def write(self, key: str, data: Any) -> None:
        path = self.path_for(key)
        self._write_sync(path, data)

    async def read(self, key: str) -> Any:
        path = self.path_for(key)
        return self._read_sync(path, key)

    async def invalidate(self, key: str) -> Path:
        path = self.path_for(key)
        exists = path.exists()
        if not exists:
            return path
        invalid = path.with_name(f"{path.name}.invalid-{time.time_ns()}")
        os.replace(path, invalid)
        return invalid

    def _write_sync(self, path: Path, data: Any) -> None:
        content = self._serialize(data)
        _atomic_write_text(path, content)

    def _read_sync(self, path: Path, key: str) -> Any:
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CorruptStoreError(f"{key}: unable to read store") from exc
        return self._deserialize(text, key)


class AtomicJsonlStore(AtomicJsonStore):
    suffix = ".jsonl"

    def _serialize(self, data: Any) -> str:
        if not isinstance(data, list):
            raise TypeError("JSONL store data must be a list")
        lines = [json.dumps({"schema_version": self.schema_version})]
        lines.extend(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in data)
        return "\n".join(lines) + "\n"

    def _deserialize(self, text: str, key: str) -> list[Any]:
        lines = text.splitlines()
        if not lines:
            raise CorruptStoreError(f"{key}: empty JSONL document")
        try:
            header = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            raise CorruptStoreError(f"{key}: invalid JSONL header") from exc
        actual = header.get("schema_version") if isinstance(header, dict) else None
        if actual != self.schema_version:
            raise SchemaVersionError(f"{key}: expected {self.schema_version}, got {actual}")
        rows: list[Any] = []
        for line_number, line in enumerate(lines[1:], start=2):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CorruptStoreError(f"{key}: invalid JSONL row {line_number}") from exc
        return rows
