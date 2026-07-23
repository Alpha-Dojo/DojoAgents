from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from dojoagents.sessions.errors import (
    BlobStoreError,
    HarnessSessionIncompatibleError,
    SessionAccessDeniedError,
    SessionConflictError,
    SessionDataCorruptError,
    SessionLeaseLostError,
    SessionNotFoundError,
    SessionStoreUnavailableError,
)
from dojoagents.sessions.models import (
    CheckpointRecord,
    SessionEvent,
    SessionMessageRecord,
    SessionPatch,
    SessionPrincipal,
    SessionScope,
)


def test_principal_requires_non_blank_user_and_has_immutable_roles():
    with pytest.raises(ValueError, match="user_id"):
        SessionPrincipal(user_id="  ")

    principal = SessionPrincipal(user_id="alice", roles=frozenset({"admin"}))
    with pytest.raises(AttributeError):
        principal.roles.add("writer")
    with pytest.raises(FrozenInstanceError):
        principal.user_id = "bob"


def test_scope_and_message_reject_blank_ids_and_negative_sequence():
    with pytest.raises(ValueError, match="session_id"):
        SessionMessageRecord(
            session_uid="uid-1",
            session_id="",
            agent_id="agent",
            sequence=0,
            role="user",
            content={"text": "hello"},
        )

    with pytest.raises(ValueError, match="sequence"):
        SessionMessageRecord(
            session_uid="uid-1",
            session_id="session-1",
            agent_id="agent",
            sequence=-1,
            role="user",
            content={"text": "hello"},
        )

    assert SessionScope(tenant_id="default", user_id="alice").user_id == "alice"


def test_persisted_records_require_utc_timestamps():
    non_utc = datetime.now(timezone(timedelta(hours=8)))
    with pytest.raises(ValueError, match="UTC"):
        SessionEvent(
            run_id="run-1",
            sequence=0,
            event_type="content.delta",
            payload={"text": "x"},
            lease_id="lease-1",
            fencing_token=1,
            created_at=non_utc,
        )

    event = SessionEvent(
        run_id="run-1",
        sequence=0,
        event_type="content.delta",
        payload={"text": "x"},
        lease_id="lease-1",
        fencing_token=1,
        created_at=datetime.now(UTC),
    )
    assert event.schema_version == 1


def test_checkpoint_payload_must_be_json_compatible():
    with pytest.raises(ValueError, match="JSON"):
        CheckpointRecord(
            session_uid="uid-1",
            session_id="session-1",
            namespace="harness:financial",
            key="state",
            payload={"bad": object()},
            version=1,
        )


def test_session_patch_cannot_change_owner_or_harness_binding():
    with pytest.raises(TypeError):
        SessionPatch(user_id="bob")
    with pytest.raises(TypeError):
        SessionPatch(harness_id="support")


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (SessionNotFoundError, "session_not_found"),
        (SessionAccessDeniedError, "session_access_denied"),
        (SessionConflictError, "session_conflict"),
        (SessionLeaseLostError, "session_lease_lost"),
        (SessionStoreUnavailableError, "session_store_unavailable"),
        (SessionDataCorruptError, "session_data_corrupt"),
        (HarnessSessionIncompatibleError, "harness_session_incompatible"),
        (BlobStoreError, "blob_store_error"),
    ],
)
def test_session_errors_have_stable_codes(error_type, code):
    error = error_type("failure")

    assert error.code == code
    assert str(error) == "failure"
