import pytest

from dojoagents.config.models import SessionsConfig
from dojoagents.sessions.errors import SessionsDisabledError
from dojoagents.sessions.models import HistoryQuery, SessionListQuery, SessionPrincipal
from dojoagents.sessions.service import SessionService


class ExplodingStore:
    def __getattr__(self, name):
        raise AssertionError(f"disabled service accessed store method {name}")


@pytest.mark.asyncio
async def test_disabled_sessions_allow_only_transient_turn_context():
    service = SessionService(store=ExplodingStore(), blob_store=ExplodingStore(), config=SessionsConfig(enabled=False))
    principal = SessionPrincipal("alice")

    transient = service.transient_turn(principal, "transient-1")

    assert transient.session_id == "transient-1"
    assert transient.persistent is False
    with pytest.raises(SessionsDisabledError) as exc:
        await service.list_sessions(principal, SessionListQuery())
    assert exc.value.code == "sessions_disabled"
    with pytest.raises(SessionsDisabledError):
        await service.history(principal, "transient-1", HistoryQuery())
    with pytest.raises(SessionsDisabledError):
        await service.export_session(principal, "transient-1")
    with pytest.raises(SessionsDisabledError):
        service.object_writer(principal, "transient-1")
    with pytest.raises(SessionsDisabledError):
        service.require_persistence("financial harness")


def test_service_methods_require_explicit_principal():
    service = SessionService(store=ExplodingStore(), blob_store=ExplodingStore(), config=SessionsConfig(enabled=False))

    with pytest.raises(TypeError):
        service.transient_turn(session_id="s1")
