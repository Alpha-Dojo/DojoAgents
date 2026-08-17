from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from typing import Protocol, runtime_checkable

from dojoagents.sessions.models import BlobRef, BlobWriteMetadata, SessionPrincipal, StoreHealth

BLOB_STORE_METHODS = (
    "startup",
    "health",
    "shutdown",
    "put",
    "open",
    "stat",
    "commit",
    "delete",
)


@runtime_checkable
class BlobStore(Protocol):
    async def startup(self) -> None: ...

    async def health(self) -> StoreHealth: ...

    async def shutdown(self) -> None: ...

    async def put(
        self,
        principal: SessionPrincipal,
        data: AsyncIterable[bytes],
        metadata: BlobWriteMetadata,
    ) -> BlobRef: ...

    async def open(self, principal: SessionPrincipal, blob_ref: BlobRef) -> AsyncIterator[bytes]: ...

    async def stat(self, principal: SessionPrincipal, blob_ref: BlobRef) -> BlobRef: ...

    async def commit(self, principal: SessionPrincipal, blob_ref: BlobRef) -> BlobRef: ...

    async def delete(self, principal: SessionPrincipal, blob_ref: BlobRef) -> None: ...
