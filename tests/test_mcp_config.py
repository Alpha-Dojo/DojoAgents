from __future__ import annotations

import tempfile
from pathlib import Path
from dojoagents.config.loader import ConfigStore

def test_load_mcp_servers_config():
    content = """
version: 1
mcp_servers:
  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    enabled: true
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "agents.yaml"
        cfg_file.write_text(content, encoding="utf-8")
        store = ConfigStore(path=cfg_file)
        config = store.snapshot()
        assert "filesystem" in config.mcp_servers
        assert config.mcp_servers["filesystem"]["command"] == "npx"
        assert config.mcp_servers["filesystem"]["enabled"] is True
