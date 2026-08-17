from dojoagents.sessions.blob_store import BLOB_STORE_METHODS, BlobStore
from dojoagents.sessions.store import SESSION_STORE_METHODS, SessionStore


def _async_method(name):
    async def method(self, *args, **kwargs):
        return None

    method.__name__ = name
    return method


CompleteSessionStore = type(
    "CompleteSessionStore",
    (),
    {name: _async_method(name) for name in SESSION_STORE_METHODS},
)
CompleteBlobStore = type(
    "CompleteBlobStore",
    (),
    {name: _async_method(name) for name in BLOB_STORE_METHODS},
)


def test_complete_session_store_fake_satisfies_protocol():
    assert isinstance(CompleteSessionStore(), SessionStore)


def test_session_store_fake_missing_each_capability_fails_conformance():
    for omitted in SESSION_STORE_METHODS:
        methods = {name: _async_method(name) for name in SESSION_STORE_METHODS if name != omitted}
        incomplete = type(f"Missing_{omitted}", (), methods)()

        assert not isinstance(incomplete, SessionStore), omitted


def test_complete_blob_store_fake_satisfies_protocol():
    assert isinstance(CompleteBlobStore(), BlobStore)


def test_blob_store_fake_missing_each_capability_fails_conformance():
    for omitted in BLOB_STORE_METHODS:
        methods = {name: _async_method(name) for name in BLOB_STORE_METHODS if name != omitted}
        incomplete = type(f"Missing_{omitted}", (), methods)()

        assert not isinstance(incomplete, BlobStore), omitted
