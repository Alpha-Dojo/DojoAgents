import pytest
from dojoagents.plugins import get_plugin_registry

@pytest.fixture(autouse=True)
def clean_registry():
    reg = get_plugin_registry()
    reg._hooks.clear()
    reg._tools.clear()
    yield
    reg._hooks.clear()
    reg._tools.clear()
