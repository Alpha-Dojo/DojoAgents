from pathlib import Path

import pytest

from dojoagents.config.models import AgentsConfig
from dojoagents.harnesses.context import (
    HarnessBuildContext,
    HarnessRuntimeContext,
    HarnessSessionContext,
    TurnContext,
)
from dojoagents.harnesses.state import HarnessRuntimeState, HarnessSessionState
from dojoagents.sessions.models import SessionPrincipal


def test_build_and_runtime_contexts_are_read_only_and_hide_raw_identity():
    build = HarnessBuildContext(
        config=AgentsConfig(),
        harness_config={"feature": True},
        config_dir=Path("/config"),
        workdir=Path("/work"),
        host="library",
        logger=object(),
    )
    runtime = HarnessRuntimeContext(capabilities=object(), services={"quotes": object()}, logger=object())

    with pytest.raises(TypeError):
        build.harness_config["feature"] = False
    with pytest.raises(TypeError):
        runtime.services["other"] = object()
    assert not hasattr(runtime, "principal")
    assert not hasattr(runtime, "session_store")
    assert not hasattr(runtime, "blob_store")


def test_sessions_and_concurrent_turns_never_share_mutable_state():
    alice = HarnessSessionContext(SessionPrincipal("alice"), "s1", HarnessSessionState())
    bob = HarnessSessionContext(SessionPrincipal("bob"), "s1", HarnessSessionState())
    first = TurnContext(request=object(), session=alice)
    second = TurnContext(request=object(), session=alice)

    alice.state.values["portfolio"] = "p-a"
    first.turn_state.values["attempt"] = 1

    assert bob.state.values == {}
    assert second.turn_state.values == {}
    assert first.tool_calls is not second.tool_calls
    assert first.tool_results is not second.tool_results


def test_state_layers_cannot_be_substituted():
    principal = SessionPrincipal("alice")
    with pytest.raises(TypeError, match="HarnessSessionState"):
        HarnessSessionContext(principal, "s1", HarnessRuntimeState())
    session = HarnessSessionContext(principal, "s1", HarnessSessionState())
    with pytest.raises(TypeError, match="HarnessTurnState"):
        TurnContext(request=object(), session=session, turn_state=HarnessSessionState())
