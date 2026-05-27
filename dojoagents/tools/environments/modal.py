import asyncio
from dojoagents.tools.environments.base import BaseEnvironment

class ModalEnvironment(BaseEnvironment):
    def __init__(self, image: str, cwd: str = "/root", timeout: int = 60):
        super().__init__(cwd=cwd, timeout=timeout)
        self.image = image
        self._started = False

    async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> asyncio.subprocess.Process:
        exec_cmd = ["modal", "sandbox", "run", "--image", self.image, "bash", "-c", cmd_string]
        return await asyncio.create_subprocess_exec(
            *exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL
        )

    def cleanup(self):
        pass
