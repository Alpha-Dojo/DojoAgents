import pytest

from dojoagents.sessions.models import cursor_scope_hash, decode_cursor, encode_cursor


def test_signed_cursor_round_trips_with_bound_scope():
    scope_hash = cursor_scope_hash("tenant-a", "alice", {"archived": False})
    payload = {
        "sort": ["2026-07-22T00:00:00+00:00", "uid-9"],
        "direction": "next",
        "scope_hash": scope_hash,
    }

    token = encode_cursor(payload, b"cursor-secret")

    assert decode_cursor(token, b"cursor-secret", scope_hash) == {"version": 1, **payload}


def test_cursor_rejects_changed_owner_scope():
    alice_scope = cursor_scope_hash("tenant-a", "alice", {"archived": False})
    bob_scope = cursor_scope_hash("tenant-a", "bob", {"archived": False})
    token = encode_cursor(
        {"sort": [10, "uid-1"], "direction": "next", "scope_hash": alice_scope},
        b"cursor-secret",
    )

    with pytest.raises(ValueError, match="scope"):
        decode_cursor(token, b"cursor-secret", bob_scope)


def test_cursor_rejects_payload_or_signature_tampering():
    scope_hash = cursor_scope_hash("default", "alice", {})
    token = encode_cursor(
        {"sort": [1], "direction": "previous", "scope_hash": scope_hash},
        b"cursor-secret",
    )
    payload, signature = token.split(".")

    with pytest.raises(ValueError, match="signature"):
        decode_cursor(f"{payload[:-1]}A.{signature}", b"cursor-secret", scope_hash)
    with pytest.raises(ValueError, match="signature"):
        decode_cursor(token, b"wrong-secret", scope_hash)


@pytest.mark.parametrize(
    "payload",
    [
        {"direction": "next", "scope_hash": "scope"},
        {"sort": [1], "direction": "sideways", "scope_hash": "scope"},
        {"sort": [1], "direction": "next"},
    ],
)
def test_cursor_requires_sort_direction_and_scope(payload):
    with pytest.raises(ValueError):
        encode_cursor(payload, b"secret")
