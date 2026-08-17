from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

import portalocker

from dojoagents.sessions.atomic import AtomicJsonStore, FileStoreError
from dojoagents.logging import LOGGER
from dojoagents.sessions.errors import BlobStoreError, SessionDataCorruptError, SessionNotFoundError
from dojoagents.sessions.models import (
    BlobRef,
    BlobWriteMetadata,
    SessionPrincipal,
    SessionScope,
    StoreHealth,
    utc_now,
)

T = TypeVar("T")


def _encode(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return _encode(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [_encode(item) for item in value]
    return value


def _decode_ref(data: dict[str, Any]) -> BlobRef:
    return BlobRef(
        **{
            **data,
            "owner": SessionScope(**data["owner"]),
            "created_at": datetime.fromisoformat(data["created_at"]),
        }
    )


def _unlink_if_exists(path: Path) -> None:
    path.unlink(missing_ok=True)


def _initialize_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _append_chunk(path: Path, chunk: bytes) -> None:
    with path.open("ab") as handle:
        handle.write(chunk)
        handle.flush()


def _finalize_file(temp_path: Path, final_path: Path) -> None:
    with temp_path.open("ab") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, final_path)
    if os.name == "posix":
        try:
            directory_fd = os.open(final_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass


class FileBlobStore:
    """Owner-scoped streaming blob storage using generated UUID paths only."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.data_root = self.root / "data"
        self.temp_root = self.root / "pending"
        self.lock_root = self.root / "locks"
        self._metadata = AtomicJsonStore(self.root / "metadata", schema_version=1)
        self._started = False

    @staticmethod
    def _validate_blob_id(blob_id: str) -> str:
        try:
            parsed = uuid.UUID(blob_id)
        except (ValueError, AttributeError) as exc:
            raise SessionNotFoundError("blob not found") from exc
        if str(parsed) != blob_id:
            raise SessionNotFoundError("blob not found")
        return blob_id

    def _data_path(self, blob_id: str) -> Path:
        return self.data_root / f"{self._validate_blob_id(blob_id)}.blob"

    def _temp_path(self, blob_id: str) -> Path:
        return self.temp_root / f"{self._validate_blob_id(blob_id)}.upload"

    def _lock_path(self, blob_id: str) -> Path:
        return self.lock_root / f"{self._validate_blob_id(blob_id)}.lock"

    def _metadata_path(self, blob_id: str) -> Path:
        return self._metadata.path_for(self._validate_blob_id(blob_id))

    def _read_record_sync(self, blob_id: str) -> dict[str, Any] | None:
        try:
            value = self._metadata._read_sync(self._metadata_path(blob_id), blob_id)
        except FileStoreError as exc:
            raise SessionDataCorruptError(str(exc)) from exc
        if value is not None and not isinstance(value, dict):
            raise SessionDataCorruptError("blob metadata must be a mapping")
        return value

    def _locked_sync(self, blob_id: str, callback: Callable[[dict[str, Any] | None], T], *, write: bool) -> T:
        self.lock_root.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(str(self._lock_path(blob_id)), mode="a+", timeout=10):
            record = self._read_record_sync(blob_id)
            result = callback(record)
            if write and record is not None:
                self._metadata._write_sync(self._metadata_path(blob_id), record)
            return result

    async def _locked(self, blob_id: str, callback: Callable[[dict[str, Any] | None], T], *, write: bool) -> T:
        return await asyncio.to_thread(self._locked_sync, blob_id, callback, write=write)

    @staticmethod
    def _authorize(record: dict[str, Any] | None, principal: SessionPrincipal) -> BlobRef:
        if record is None:
            raise SessionNotFoundError("blob not found")
        ref = _decode_ref(record["ref"])
        if ref.owner != SessionScope.from_principal(principal):
            raise SessionNotFoundError("blob not found")
        return ref

    async def startup(self) -> None:
        await asyncio.to_thread(self.root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.data_root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.temp_root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.lock_root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self._metadata.root.mkdir, parents=True, exist_ok=True)
        self._started = True

    async def health(self) -> StoreHealth:
        try:
            await self.startup()
            return StoreHealth(healthy=True, provider="file", schema_version=1)
        except Exception as exc:
            LOGGER.exception("FileBlobStore health check failed")
            return StoreHealth(healthy=False, provider="file", schema_version=1, detail=str(exc))

    async def shutdown(self) -> None:
        self._started = False

    async def put(self, principal: SessionPrincipal, data, metadata: BlobWriteMetadata) -> BlobRef:
        await self.startup()
        blob_id = str(uuid.uuid4())
        created_at = utc_now()
        pending = BlobRef(blob_id=blob_id, owner=SessionScope.from_principal(principal), created_at=created_at)
        initial_record = {
            "ref": _encode(pending),
            "write_metadata": _encode(metadata),
            "data_ready": False,
            "updated_at": created_at.isoformat(),
        }

        def reserve(record: dict[str, Any] | None) -> None:
            if record is not None:
                raise BlobStoreError("generated blob id collision")
            self._metadata._write_sync(self._metadata_path(blob_id), initial_record)

        await self._locked(blob_id, reserve, write=False)
        temp_path = self._temp_path(blob_id)
        digest = hashlib.sha256()
        size = 0
        try:
            await asyncio.to_thread(_initialize_file, temp_path)
            async for chunk in data:
                if not isinstance(chunk, bytes):
                    raise TypeError("blob stream chunks must be bytes")
                digest.update(chunk)
                size += len(chunk)
                await asyncio.to_thread(_append_chunk, temp_path, chunk)
            await asyncio.to_thread(_finalize_file, temp_path, self._data_path(blob_id))
            completed_pending = replace(pending, checksum_sha256=digest.hexdigest(), size_bytes=size)

            def mark_ready(record: dict[str, Any] | None) -> None:
                if record is None:
                    raise BlobStoreError("blob metadata disappeared during upload")
                record["ref"] = _encode(completed_pending)
                record["data_ready"] = True
                record["updated_at"] = utc_now().isoformat()

            await self._locked(blob_id, mark_ready, write=True)
            return completed_pending
        except Exception as exc:
            if isinstance(exc, BlobStoreError):
                raise
            raise BlobStoreError(f"blob upload interrupted: {exc}") from exc

    async def open(self, principal: SessionPrincipal, blob_ref: BlobRef):
        def inspect(record: dict[str, Any] | None) -> tuple[BlobRef, bool]:
            current = self._authorize(record, principal)
            return current, bool(record["data_ready"])

        current, data_ready = await self._locked(blob_ref.blob_id, inspect, write=False)
        if current.state == "deleted" or not data_ready:
            raise BlobStoreError("blob data is not available")
        path = self._data_path(current.blob_id)

        async def chunks():
            handle = await asyncio.to_thread(path.open, "rb")
            try:
                while True:
                    chunk = await asyncio.to_thread(handle.read, 64 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await asyncio.to_thread(handle.close)

        return chunks()

    async def stat(self, principal: SessionPrincipal, blob_ref: BlobRef) -> BlobRef:
        return await self._locked(blob_ref.blob_id, lambda record: self._authorize(record, principal), write=False)

    async def commit(self, principal: SessionPrincipal, blob_ref: BlobRef) -> BlobRef:
        def operation(record: dict[str, Any] | None) -> BlobRef:
            current = self._authorize(record, principal)
            if current.state == "committed":
                return current
            if current.state == "deleted" or not record["data_ready"]:
                raise BlobStoreError("pending blob is not ready to commit")
            committed = replace(current, state="committed")
            record["ref"] = _encode(committed)
            record["updated_at"] = utc_now().isoformat()
            return committed

        return await self._locked(blob_ref.blob_id, operation, write=True)

    async def delete(self, principal: SessionPrincipal, blob_ref: BlobRef) -> None:
        def tombstone(record: dict[str, Any] | None) -> BlobRef:
            current = self._authorize(record, principal)
            if current.state != "deleted":
                current = replace(current, state="deleted")
                record["ref"] = _encode(current)
                record["updated_at"] = utc_now().isoformat()
            return current

        current = await self._locked(blob_ref.blob_id, tombstone, write=True)
        try:
            await asyncio.to_thread(_unlink_if_exists, self._data_path(current.blob_id))
            await asyncio.to_thread(_unlink_if_exists, self._temp_path(current.blob_id))
        except OSError as exc:
            raise BlobStoreError(f"blob soft-delete pending: {exc}") from exc

    async def _metadata_ids(self) -> list[str]:
        def scan() -> list[str]:
            if not self._metadata.root.exists():
                return []
            return [path.stem for path in self._metadata.root.glob("*.json")]

        return await asyncio.to_thread(scan)

    async def collect_expired_pending(self, now: datetime) -> int:
        removed = 0
        for blob_id in await self._metadata_ids():

            def inspect(record: dict[str, Any] | None) -> bool:
                if record is None:
                    return False
                ref = _decode_ref(record["ref"])
                if ref.state != "pending" or ref.created_at >= now:
                    return False
                record["ref"] = _encode(replace(ref, state="deleted"))
                record["updated_at"] = utc_now().isoformat()
                return True

            try:
                expired = await self._locked(blob_id, inspect, write=True)
                if not expired:
                    continue
                await asyncio.to_thread(_unlink_if_exists, self._data_path(blob_id))
                await asyncio.to_thread(_unlink_if_exists, self._temp_path(blob_id))
                removed += 1
            except Exception:
                LOGGER.exception("Failed to collect pending blob %s", blob_id)
        return removed

    async def retry_soft_deleted(self, limit: int) -> int:
        if limit <= 0:
            return 0
        retried = 0
        for blob_id in await self._metadata_ids():
            if retried >= limit:
                break
            try:
                record = await self._locked(blob_id, lambda item: item, write=False)
                if record is None or _decode_ref(record["ref"]).state != "deleted":
                    continue
                await asyncio.to_thread(_unlink_if_exists, self._data_path(blob_id))
                await asyncio.to_thread(_unlink_if_exists, self._temp_path(blob_id))
                retried += 1
            except Exception:
                LOGGER.exception("Failed to retry soft-deleted blob %s", blob_id)
        return retried
