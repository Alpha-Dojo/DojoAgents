"""Deprecated import facade for domain-neutral session atomic primitives."""

from dojoagents.sessions.atomic import (
    AtomicJsonStore,
    AtomicJsonlStore,
    CorruptStoreError,
    FileStoreError,
    InvalidStoreKeyError,
    SchemaVersionError,
    _atomic_write_bytes,
    _atomic_write_text,
)

__all__ = [
    "AtomicJsonStore",
    "AtomicJsonlStore",
    "CorruptStoreError",
    "FileStoreError",
    "InvalidStoreKeyError",
    "SchemaVersionError",
    "_atomic_write_bytes",
    "_atomic_write_text",
]
