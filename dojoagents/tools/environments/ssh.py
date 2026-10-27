import shlex

from dojoagents.tools import processes
from dojoagents.tools.environments.base import BaseEnvironment


class SSHEnvironment(BaseEnvironment):
    def __init__(self, host: str, user: str, port: int = 22, cwd: str = "~"):
        super().__init__(cwd=cwd)
        self.host = host
        self.user = user
        self.port = port

    async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> processes.Process:
        ssh_target = f"{self.user}@{self.host}"
        quoted_cmd = shlex.quote(cmd_string)
        exec_cmd = ["ssh", "-p", str(self.port), ssh_target, f"bash -c {quoted_cmd}"]
        return await processes.open_process(
            exec_cmd,
            stdin=processes.PIPE if stdin_data else processes.DEVNULL,
            stdout=processes.PIPE,
            stderr=processes.STDOUT,
        )

    def cleanup(self):
        pass
