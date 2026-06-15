import pytest
from dojoagents.plugins import get_plugin_registry
from dojoagents.utils.event_bus import event_bus

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
