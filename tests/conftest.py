import pytest
from dojoagents.plugins import get_plugin_registry
from dojoagents.utils.event_bus import event_bus


@pytest.fixture
def anyio_backend() -> str:
    """Pin new AnyIO tests to the asyncio backend.

    The migration runs on the asyncio backend only; Trio is neither a declared
    dependency nor a supported backend, and no test may assume it is importable.
    """

    return "asyncio"


@pytest.fixture(autouse=True)
def clean_registry():
    reg = get_plugin_registry()
    reg._hooks.clear()
    reg._tools.clear()
    event_bus.clear()
    yield
    reg._hooks.clear()
    reg._tools.clear()
    event_bus.clear()
