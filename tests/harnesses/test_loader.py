import pytest

from dojoagents.config.models import HarnessConfig
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.harnesses.errors import InvalidHarnessError
from dojoagents.harnesses.loader import HarnessLoadError, HarnessLoader


class FixtureHarness:
    descriptor = HarnessDescriptor("fixture", "1", "Fixture")

    def configure(self, builder, context):
        return None

    async def startup(self, context):
        return None

    async def shutdown(self, context):
        return None


def create_fixture(config, context):
    assert config == {"mode": "test"}
    return FixtureHarness()


def create_wrong_contract():
    return object()


def test_loader_resolves_exact_factory_and_alias():
    exact = HarnessLoader().load(
        HarnessConfig(
            id="fixture",
            factory="tests.harnesses.test_loader:create_fixture",
            config={"mode": "test"},
        ),
        context=object(),
    )
    alias = HarnessLoader(aliases={"fixture": "tests.harnesses.test_loader:FixtureHarness"}).load(HarnessConfig(id="fixture", factory=None), context=object())

    assert isinstance(exact.harness, FixtureHarness)
    assert exact.resolved_factory.endswith(":create_fixture")
    assert isinstance(alias.harness, FixtureHarness)


def test_loader_rejects_descriptor_mismatch_wrong_contract_and_module_error_without_secrets():
    with pytest.raises(InvalidHarnessError, match=r"expected.*other.*fixture"):
        HarnessLoader().load(
            HarnessConfig(id="other", factory="tests.harnesses.test_loader:FixtureHarness"),
            context=object(),
        )
    with pytest.raises(InvalidHarnessError, match="descriptor"):
        HarnessLoader().load(
            HarnessConfig(id="fixture", factory="tests.harnesses.test_loader:create_wrong_contract"),
            context=object(),
        )

    secret = "super-secret-token"
    with pytest.raises(HarnessLoadError) as failure:
        HarnessLoader().load(
            HarnessConfig(id="missing", factory="does.not.exist:create", config={"token": secret}),
            context=object(),
        )
    assert secret not in str(failure.value)


def test_loader_requires_explicit_attribute_path():
    with pytest.raises(HarnessLoadError, match="module:attribute"):
        HarnessLoader().load(HarnessConfig(id="fixture", factory="tests.harnesses.test_loader"))
