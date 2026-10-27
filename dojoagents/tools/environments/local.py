from __future__ import annotations

from dojoagents.tools import processes
from dojoagents.tools.environments.base import BaseEnvironment
from dojoagents.tools.sandbox import SandboxPolicy


class LocalEnvironment(BaseEnvironment):
    def __init__(self, policy: SandboxPolicy, cwd: str = ".") -> None:
        super().__init__(cwd=cwd)
        self.policy = policy

    async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> processes.Process:
        self.policy.check_tool("terminal")

        return await processes.open_process(
            cmd_string,
            stdin=processes.PIPE if stdin_data else processes.DEVNULL,
            stdout=processes.PIPE,
            stderr=processes.STDOUT,
            env=self.env_vars,
        )
