import asyncio
import shlex
from dojoagents.tools.environments.base import BaseEnvironment

class SSHEnvironment(BaseEnvironment):
    def __init__(self, host: str, user: str, port: int = 22, cwd: str = "~"):
        super().__init__(cwd=cwd)
        self.host = host
        self.user = user
        self.port = port

    async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> asyncio.subprocess.Process:
        ssh_target = f"{self.user}@{self.host}"
        quoted_cmd = shlex.quote(cmd_string)
        exec_cmd = ["ssh", "-p", str(self.port), ssh_target, f"bash -c {quoted_cmd}"]
        return await asyncio.create_subprocess_exec(
            *exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL
        )

    def cleanup(self):
        pass
