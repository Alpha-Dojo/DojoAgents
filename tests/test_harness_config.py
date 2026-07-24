import pytest

from dojoagents.config.loader import ConfigStore, _to_config
from dojoagents.config.models import AgentsConfig


def test_harness_defaults_to_built_in_financial_factory():
    harness = AgentsConfig().harness

    assert harness.id == "financial"
    assert harness.factory == "dojoagents.harnesses.built_in.financial:create_harness"
    assert harness.manifest is None


def test_harness_relative_paths_resolve_from_config_file(tmp_path):
    config_dir = tmp_path / "deployment"
    config_dir.mkdir()
    config_path = config_dir / "agents.yaml"
    config_path.write_text(
        """
harness:
  id: support
  factory: null
  manifest: ./harness.yaml
  extra_skill_dirs: [./skills]
  extra_tool_dirs: [../shared-tools]
""".strip(),
        encoding="utf-8",
    )

    harness = ConfigStore(config_path).snapshot().harness

    assert harness.id == "support"
    assert harness.factory is None
    assert harness.manifest == str((config_dir / "harness.yaml").resolve())
    assert harness.extra_skill_dirs == [str((config_dir / "skills").resolve())]
    assert harness.extra_tool_dirs == [str((config_dir / "../shared-tools").resolve())]


@pytest.mark.parametrize(
    "harness",
    [
        {"id": "bad", "factory": "pkg:create", "manifest": "manifest.yaml"},
        {"id": "bad", "factory": None, "manifest": None},
    ],
)
def test_harness_requires_exactly_one_loading_source(harness):
    with pytest.raises(ValueError, match="exactly one"):
        _to_config({"harness": harness})


def test_harness_rejects_unknown_keys():
    with pytest.raises(ValueError, match="unknown"):
        _to_config({"harness": {"id": "financial", "factory": "pkg:create", "typo": True}})


def test_harness_config_and_extra_dirs_are_loaded():
    harness = _to_config(
        {
            "harness": {
                "id": "project",
                "factory": "project.harness:create_harness",
                "config": {"feature": True},
                "extra_skill_dirs": ["/srv/skills"],
                "extra_tool_dirs": ["/srv/tools"],
            }
        }
    ).harness

    assert harness.config == {"feature": True}
    assert harness.extra_skill_dirs == ["/srv/skills"]
    assert harness.extra_tool_dirs == ["/srv/tools"]
