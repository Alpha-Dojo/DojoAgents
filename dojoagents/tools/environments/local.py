from __future__ import annotations
import asyncio
from dojoagents.tools.environments.base import BaseEnvironment
from dojoagents.tools.sandbox import SandboxPolicy


class LocalEnvironment(BaseEnvironment):
    def __init__(self, policy: SandboxPolicy, cwd: str = ".") -> None:
        super().__init__(cwd=cwd)
        self.policy = policy

    async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> asyncio.subprocess.Process:
        self.policy.check_tool("terminal")

        return await asyncio.create_subprocess_shell(
            cmd_string,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL,
            env=self.env_vars,
        )
