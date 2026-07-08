import asyncio
import uuid
import atexit
import contextvars
from dataclasses import dataclass, field
from typing import Any, Dict

from dojoagents.logging import LOGGER

# Context variable to track active session ID (typically session key) during tool execution
active_session_id = contextvars.ContextVar("active_session_id", default="")
# Latest user message for the active agent run (order intent resolution, etc.)
active_user_message = contextvars.ContextVar("active_user_message", default="")


@dataclass
class WriteSessionFileGuardContext:
    llm_provider: Any
    model: str
    user_message: str = ""
    request_metadata: dict[str, Any] = field(default_factory=dict)
    history: list | None = None
    enabled: bool = True


active_write_session_file_guard = contextvars.ContextVar(
    "active_write_session_file_guard",
    default=None,
)


class BackgroundProcessSession:
    def __init__(self, session_id: str, process: asyncio.subprocess.Process, command: str):
        self.id = session_id
        self.process = process
        self.command = command
        self.notify_on_complete = False
        self.output_buffer = ""
        self.session_key = ""

    async def wait(self):
        try:
            await self.process.wait()
        except Exception:
            pass

    def terminate(self):
        try:
            self.process.terminate()
        except OSError:
            pass

    def kill(self):
        try:
            self.process.kill()
        except OSError:
            pass


class AsyncProcessRegistry:
    def __init__(self):
        self.processes: Dict[str, BackgroundProcessSession] = {}
        self.completion_queue = asyncio.Queue()

    async def spawn(self, command: str, env_vars: dict = None) -> BackgroundProcessSession:
        session_id = uuid.uuid4().hex[:12]
        process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, stdin=asyncio.subprocess.DEVNULL, env=env_vars)
        session = BackgroundProcessSession(session_id, process, command)
        self.processes[session_id] = session

        asyncio.create_task(self._read_stdout(session))
        asyncio.create_task(self._reap_process(session_id))
        return session

    async def _read_stdout(self, session: BackgroundProcessSession):
        try:
            while True:
                line = await session.process.stdout.readline()
                if not line:
                    break
                session.output_buffer += line.decode("utf-8", errors="replace")
        except Exception:
            pass

    async def _reap_process(self, session_id: str):
        session = self.processes.get(session_id)
        if session:
            await session.wait()
            # Give a tiny bit of time for the stdout reader to finish reading remaining buffer
            await asyncio.sleep(0.05)
            if getattr(session, "notify_on_complete", False):
                event = {
                    "type": "completion",
                    "session_id": session.id,
                    "command": session.command,
                    "exit_code": session.process.returncode,
                    "output": getattr(session, "output_buffer", ""),
                    "session_key": getattr(session, "session_key", ""),
                }
                await self.completion_queue.put(event)
            self.processes.pop(session_id, None)

    def has_active_processes(self) -> bool:
        return len(self.processes) > 0

    def cleanup(self):
        """同步强杀所有已注册的子进程，用于进程退出或终结时"""
        if not self.processes:
            return
        LOGGER.info("Cleaning up %d background process(es)...", len(self.processes))
        for session in list(self.processes.values()):
            session.kill()
        self.processes.clear()


# 全局进程注册中心单例
process_registry = AsyncProcessRegistry()


def _global_atexit_cleanup():
    process_registry.cleanup()


atexit.register(_global_atexit_cleanup)
