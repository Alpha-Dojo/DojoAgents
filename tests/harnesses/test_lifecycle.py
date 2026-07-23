import pytest

from dojoagents.harnesses.capabilities import ServiceSpec
from dojoagents.harnesses.errors import HarnessLifecycleError
from dojoagents.harnesses.lifecycle import ExternalServiceBinding, LifecycleManager


class Service:
    def __init__(self, name, events, *, healthy=True, fail=False):
        self.name = name
        self.events = events
        self.healthy = healthy
        self.fail = fail

    async def startup(self):
        self.events.append(f"start:{self.name}")
        if self.fail:
            raise RuntimeError("boom")

    async def health(self):
        return self.healthy

    async def shutdown(self):
        self.events.append(f"stop:{self.name}")


@pytest.mark.asyncio
async def test_services_start_topologically_and_shutdown_reverse_idempotently():
    events = []
    manager = LifecycleManager(
        (
            ServiceSpec("api", "harness:a", factory=lambda: Service("api", events), dependencies=("db",)),
            ServiceSpec("db", "harness:a", factory=lambda: Service("db", events)),
        )
    )

    services = await manager.startup()
    await manager.shutdown()
    await manager.shutdown()

    assert tuple(services) == ("db", "api")
    assert events == ["start:db", "start:api", "stop:api", "stop:db"]


@pytest.mark.asyncio
async def test_startup_failure_rolls_back_started_services():
    events = []
    manager = LifecycleManager(
        (
            ServiceSpec("db", "harness:a", factory=lambda: Service("db", events)),
            ServiceSpec(
                "api",
                "harness:a",
                factory=lambda: Service("api", events, fail=True),
                dependencies=("db",),
            ),
        )
    )

    with pytest.raises(HarnessLifecycleError, match="api"):
        await manager.startup()

    assert events == ["start:db", "start:api", "stop:api", "stop:db"]


@pytest.mark.asyncio
async def test_unhealthy_service_and_dependency_cycle_are_errors():
    events = []
    unhealthy = LifecycleManager((ServiceSpec("db", "harness:a", factory=lambda: Service("db", events, healthy=False)),))
    with pytest.raises(HarnessLifecycleError, match="health"):
        await unhealthy.startup()
    assert events == ["start:db", "stop:db"]

    cycle = LifecycleManager(
        (
            ServiceSpec("a", "harness:a", factory=lambda: Service("a", []), dependencies=("b",)),
            ServiceSpec("b", "harness:a", factory=lambda: Service("b", []), dependencies=("a",)),
        )
    )
    with pytest.raises(HarnessLifecycleError, match="cycle"):
        await cycle.startup()


@pytest.mark.asyncio
async def test_external_service_binding_obeys_lifecycle_ownership():
    events = []
    external = Service("external", events)
    manager = LifecycleManager(
        (ServiceSpec("db", "harness:a", factory=lambda: Service("default", events)),),
        {"db": ExternalServiceBinding(external)},
    )

    services = await manager.startup()
    await manager.shutdown()

    assert services["db"] is external
    assert events == []

    owned = LifecycleManager(
        (ServiceSpec("db", "harness:a", factory=lambda: Service("default", events)),),
        {"db": ExternalServiceBinding(external, runtime_owns_lifecycle=True)},
    )
    await owned.startup()
    await owned.shutdown()
    assert events == ["start:external", "stop:external"]


def test_external_service_binding_rejects_undeclared_ids():
    with pytest.raises(HarnessLifecycleError, match="not declared"):
        LifecycleManager(
            (ServiceSpec("db", "harness:a", factory=lambda: object()),),
            {"unknown": ExternalServiceBinding(object())},
        )
