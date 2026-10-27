from dojoagents.tools import processes
from dojoagents.tools.environments.base import BaseEnvironment


class ModalEnvironment(BaseEnvironment):
    def __init__(self, image: str, cwd: str = "/root", timeout: int = 60):
        super().__init__(cwd=cwd, timeout=timeout)
        self.image = image
        self._started = False

    async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> processes.Process:
        exec_cmd = ["modal", "sandbox", "run", "--image", self.image, "bash", "-c", cmd_string]
        return await processes.open_process(
            exec_cmd,
            stdin=processes.PIPE if stdin_data else processes.DEVNULL,
            stdout=processes.PIPE,
            stderr=processes.STDOUT,
        )

    def cleanup(self):
        pass
