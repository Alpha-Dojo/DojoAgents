from dojoagents.tools import processes
from dojoagents.tools.environments.base import BaseEnvironment


class DockerEnvironment(BaseEnvironment):
    def __init__(self, image: str, cwd: str = "/workspace", container_name: str = None):
        super().__init__(cwd=cwd)
        self.image = image
        self.container_name = container_name or f"dojo-sandbox-{self._session_id}"
        self._started = False

    async def _ensure_container(self):
        if self._started:
            return
        # 自动挂载宿主机当前工作目录至容器的 /workspace
        import os

        host_cwd = os.getcwd()
        start_cmd = ["docker", "run", "-d", "--name", self.container_name, "-v", f"{host_cwd}:/workspace", "--workdir", "/workspace", self.image, "tail", "-f", "/dev/null"]
        # 短命令：只关心退出码，不需要流式读取
        await processes.run_process(start_cmd, stdout=processes.PIPE, stderr=processes.PIPE)
        self._started = True

    async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> processes.Process:
        await self._ensure_container()
        exec_cmd = ["docker", "exec", "-i", self.container_name, "bash", "-c", cmd_string]
        return await processes.open_process(
            exec_cmd,
            stdin=processes.PIPE if stdin_data else processes.DEVNULL,
            stdout=processes.PIPE,
            stderr=processes.STDOUT,
        )

    def cleanup(self):
        if self._started:
            import subprocess

            subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True)
