import anyio
import atexit
import contextvars
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict

from dojoagents.logging import LOGGER
from dojoagents.tools import processes
from dojoagents.utils.detached_tasks import start_detached

# Context variable to track active session ID (typically session key) during tool execution
active_session_id = contextvars.ContextVar("active_session_id", default="")
active_session_principal = contextvars.ContextVar("active_session_principal", default=None)
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
    """One registered background child process.

    The process handle is the unified :class:`dojoagents.tools.processes.Process`
    adapter; the session adds the bookkeeping the ``terminal`` tool needs
    (``session_key`` / ``notify_on_complete`` / accumulated ``output_buffer``).
    """

    def __init__(self, session_id: str, process: processes.Process, command: str):
        self.id = session_id
        self.process = process
        self.command = command
        self.notify_on_complete = False
        self.output_buffer = ""
        self.session_key = ""
        self._output_drained = anyio.Event()

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    async def wait(self):
        try:
            return await self.process.wait()
        except Exception:
            return self.process.returncode

    def terminate(self):
        self.process.terminate()

    def kill(self):
        self.process.kill()

    async def wait_for_output_drain(self, *, timeout: float = 5.0) -> None:
        """Wait (bounded) for the stdout reader to observe EOF."""
        with anyio.move_on_after(timeout):
            await self._output_drained.wait()


class AsyncProcessRegistry:
    def __init__(self):
        self.processes: Dict[str, BackgroundProcessSession] = {}
        self._completion_send, self.completion_events = anyio.create_memory_object_stream[dict[str, Any]](
            max_buffer_size=32
        )

    async def spawn(self, command: str, env_vars: dict = None) -> BackgroundProcessSession:
        session_id = uuid.uuid4().hex[:12]
        process = await processes.open_process(
            command,
            stdin=processes.DEVNULL,
            stdout=processes.PIPE,
            stderr=processes.STDOUT,
            env=env_vars,
        )
        session = BackgroundProcessSession(session_id, process, command)
        self.processes[session_id] = session

        # The drainer and the reaper must outlive this call: the tool call
        # returns immediately while the child keeps running, and the enclosing
        # request may well end first.  AnyIO has no fire-and-forget primitive, so
        # ownership is handed to the audited detached-task boundary.
        start_detached(self._drain_stdout(session), name=f"dojo-bg-stdout:{session_id}")
        start_detached(self._reap_process(session), name=f"dojo-bg-reap:{session_id}")
        return session

    async def _drain_stdout(self, session: BackgroundProcessSession) -> None:
        """Read the child's stdout to EOF, then release the reaper."""
        try:
            async for chunk in session.process.read_stdout():
                session.output_buffer += chunk.decode("utf-8", errors="replace")
        except Exception:
            LOGGER.debug("Background stdout reader stopped early: session=%s", session.id)
        finally:
            session._output_drained.set()

    async def _reap_process(self, session: BackgroundProcessSession) -> None:
        """Await exit, publish the completion event, then deregister.

        The session object is held directly instead of being looked up in
        ``self.processes``: :meth:`has_active_processes` prunes exited sessions,
        and a prune that won the race must not swallow the completion event.
        """
        try:
            await session.wait()
            await session.wait_for_output_drain()
            if session.notify_on_complete:
                event = {
                    "type": "completion",
                    "session_id": session.id,
                    "command": session.command,
                    "exit_code": session.process.returncode,
                    "output": session.output_buffer,
                    "session_key": session.session_key,
                }
                try:
                    await self._completion_send.send(event)
                except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                    LOGGER.debug("Completion stream closed; dropping event for session=%s", session.id)
        except Exception:
            LOGGER.exception("Background process reaper failed: session=%s", session.id)
        finally:
            self.processes.pop(session.id, None)

    def _prune_exited(self) -> None:
        """Drop sessions whose child already exited.

        A reaper that never runs (for example because its detached task was
        discarded) must not leave the registry reporting phantom activity.
        """
        for session_id in [sid for sid, session in self.processes.items() if session.returncode is not None]:
            self.processes.pop(session_id, None)

    def has_active_processes(self) -> bool:
        self._prune_exited()
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
