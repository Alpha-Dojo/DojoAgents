import anyio
import os
import shlex
from abc import ABC, abstractmethod

from dojoagents.tools import processes


class BaseEnvironment(ABC):
    def __init__(self, cwd: str, timeout: float = 120.0):
        self.cwd = os.path.realpath(os.path.abspath(os.path.expanduser(cwd)))
        self.timeout = timeout
        self._session_id = os.urandom(6).hex()
        self.env_vars = os.environ.copy()

    @abstractmethod
    async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> processes.Process:
        pass

    async def execute(self, command: str, timeout: float = None) -> dict:
        eff_timeout = timeout or self.timeout
        cwd_marker = f"__DOJO_CWD_{self._session_id}__"
        cwd_file = f"/tmp/dojo-cwd-{self._session_id}.txt"

        wrapped_command = (
            f"cd {shlex.quote(self.cwd)} || exit 126\n"
            f"{command}\n"
            f"__exit_code=$?\n"
            f"pwd -P > {cwd_file} 2>/dev/null || true\n"
            f"printf '\\n{cwd_marker}%s{cwd_marker}\\n' \"$(pwd -P)\"\n"
            f"exit $__exit_code"
        )

        process = await self._run_bash(wrapped_command, eff_timeout)
        cancelled_exc = anyio.get_cancelled_exc_class()
        try:
            with anyio.fail_after(eff_timeout):
                stdout_bytes, _ = await process.communicate()
            output = stdout_bytes.decode("utf-8", errors="replace")
            from dojoagents.agent.redact import redact_sensitive_text

            output = redact_sensitive_text(output)
            returncode = process.returncode
        except TimeoutError:
            await self._stop_process(process)
            return {"output": "Command timed out", "exit_code": 124}
        except cancelled_exc:
            await self._stop_process(process)
            raise

        if cwd_marker in output:
            parts = output.split(cwd_marker)
            if len(parts) >= 3:
                new_cwd = parts[-2].strip()
                if os.path.isdir(new_cwd):
                    self.cwd = new_cwd
                output = parts[0] + parts[-1]

        return {
            "output": output.strip(),
            "exit_code": returncode if returncode is not None else 0,
        }

    @staticmethod
    async def _stop_process(process: processes.Process) -> None:
        """Kill and reap a child without letting caller cancellation skip cleanup."""

        await processes.terminate_then_kill(process)
