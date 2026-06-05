# tests/test_skills_claude_toggle.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from dojoagents.agent.runtime import Runtime
from dojoagents.config.loader import ConfigStore, _to_config


def test_skills_config_loader_default_value():
    """Verify that read_claude_skills defaults to False in loader and models."""
    raw_config = {}
    config = _to_config(raw_config)
    assert config.skills.read_claude_skills is False


def test_skills_config_loader_custom_value():
    """Verify that read_claude_skills can be parsed as True from raw config dict."""
    raw_config = {
        "skills": {
            "read_claude_skills": True
        }
    }
    config = _to_config(raw_config)
    assert config.skills.read_claude_skills is True


def test_skills_claude_path_toggle_enabled():
    """Verify that ~/.claude/skills is appended when read_claude_skills is True."""
    # Obtain a default config and set read_claude_skills to True
    raw_config = {
        "skills": {
            "read_claude_skills": True
        }
    }
    config = _to_config(raw_config)
    
    mock_store = MagicMock(spec=ConfigStore)
    mock_store.snapshot.return_value = config
    
    runtime = Runtime.from_config_store(mock_store)
    
    # Assert that ~/.claude/skills is in the skill_manager paths
    expected_path = Path("~/.claude/skills").expanduser()
    assert expected_path in runtime.agent.skill_manager.skill_dirs


def test_skills_claude_path_toggle_disabled():
    """Verify that ~/.claude/skills is not appended when read_claude_skills is False."""
    raw_config = {
        "skills": {
            "read_claude_skills": False
        }
    }
    config = _to_config(raw_config)
    
    mock_store = MagicMock(spec=ConfigStore)
    mock_store.snapshot.return_value = config
    
    runtime = Runtime.from_config_store(mock_store)
    
    expected_path = Path("~/.claude/skills").expanduser()
    assert expected_path not in runtime.agent.skill_manager.skill_dirs
