"""Unified child-process adapter built on AnyIO.

Business modules must not import or annotate ``asyncio.subprocess`` types.  This
module is the single entry point for spawning, observing and reaping child
processes.

Usage rules
-----------
* Short, non-interactive command -> :func:`run_process`, a thin wrapper over
  ``anyio.run_process``.
* Streaming, interactive or long-lived process -> :func:`open_process`, a thin
  wrapper over ``anyio.open_process`` returning a :class:`Process` that exposes
  ``pid`` / ``returncode`` / ``wait()`` / ``communicate()`` / ``terminate()`` /
  ``kill()`` plus stdin writes and stdout/stderr stream reads.
* Cancellation or timeout -> :func:`terminate_then_kill`, which performs
  terminate -> grace period -> kill -> reap under a shielded cancel scope so a
  cancelled or timed-out parent never leaks an orphan child.

Why the adapter exists
----------------------
``anyio``'s process object deliberately mirrors only the low-level surface:

* there is no ``communicate()``; both pipes must be drained concurrently, and
* the byte streams raise ``anyio.EndOfStream`` at EOF instead of returning
  ``b""`` the way ``asyncio``'s ``StreamReader`` does, and
* a string command is executed through the platform shell while a sequence is
  executed directly, so call sites must be explicit about which they pass.

:class:`Process` restores the subprocess-style contract the rest of the
codebase relies on without re-introducing an ``asyncio.subprocess`` dependency.
"""

from __future__ import annotations

import subprocess
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import IO, Any

import anyio

from dojoagents.logging import LOGGER

# Re-exported stdlib stream selectors so business modules never import
# ``subprocess`` just to ask for a pipe.
PIPE = subprocess.PIPE
DEVNULL = subprocess.DEVNULL
STDOUT = subprocess.STDOUT
# ``None`` means "inherit the parent's stream" (the stdlib default).
INHERIT: None = None

DEFAULT_MAX_LINE_BYTES = 4 * 1024 * 1024
DEFAULT_TERMINATE_GRACE_SECONDS = 5.0


@dataclass(frozen=True)
class ProcessResult:
    """Outcome of a short command run through :func:`run_process`."""

    command: str | tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Process:
    """A child process with a subprocess-compatible surface on top of AnyIO.

    Instances are created by :func:`open_process`.  The wrapper is intentionally
    thin: it forwards to the AnyIO process and only adds the behaviour AnyIO
    does not provide (``communicate()``, decoded stream helpers, idempotent
    termination).
    """

    def __init__(self, process: anyio.abc.Process) -> None:
        self._process = process

    def __repr__(self) -> str:
        return f"<Process pid={self.pid} returncode={self.returncode}>"

    @property
    def pid(self) -> int:
        return self._process.pid

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    @property
    def stdin(self) -> anyio.abc.ByteSendStream | None:
        return self._process.stdin

    @property
    def stdout(self) -> anyio.abc.ByteReceiveStream | None:
        return self._process.stdout

    @property
    def stderr(self) -> anyio.abc.ByteReceiveStream | None:
        return self._process.stderr

    async def wait(self) -> int:
        """Wait for exit and return the exit code."""
        return await self._process.wait()

    async def communicate(self, input: bytes | str | None = None) -> tuple[bytes, bytes]:
        """Drain stdout/stderr to EOF (optionally feeding stdin) and reap.

        Mirrors ``asyncio.subprocess.Process.communicate``: stdin is always
        closed, both captured pipes are read concurrently so a child cannot
        deadlock on a full pipe, and the process is awaited before returning.
        Streams that were not captured (``DEVNULL`` or inherited) are skipped.
        """
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []

        async def _feed_stdin() -> None:
            stream = self._process.stdin
            if stream is None:
                return
            try:
                if input:
                    await stream.send(input.encode("utf-8") if isinstance(input, str) else input)
            except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                pass
            finally:
                try:
                    await stream.aclose()
                except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                    pass

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(_feed_stdin)
            task_group.start_soon(_drain_stream, self._process.stdout, stdout_chunks)
            task_group.start_soon(_drain_stream, self._process.stderr, stderr_chunks)

        await self.wait()
        return b"".join(stdout_chunks), b"".join(stderr_chunks)

    async def read_stdout(self) -> AsyncIterator[bytes]:
        """Yield stdout chunks until EOF."""
        async for chunk in _iter_stream(self._process.stdout):
            yield chunk

    async def read_stderr(self) -> AsyncIterator[bytes]:
        """Yield stderr chunks until EOF."""
        async for chunk in _iter_stream(self._process.stderr):
            yield chunk

    async def iter_lines(
        self,
        source: str = "stdout",
        *,
        encoding: str = "utf-8",
        max_line_bytes: int = DEFAULT_MAX_LINE_BYTES,
    ) -> AsyncIterator[str]:
        """Yield decoded lines from ``source`` (``"stdout"`` or ``"stderr"``).

        Replaces ``asyncio``'s ``StreamReader.readline()`` loop: lines are
        yielded without their trailing newline, EOF terminates the iterator, and
        a single line larger than ``max_line_bytes`` raises ``ValueError``
        instead of growing the buffer without bound.
        """
        if source == "stdout":
            stream = self._process.stdout
        elif source == "stderr":
            stream = self._process.stderr
        else:
            raise ValueError("source must be 'stdout' or 'stderr'")

        buffer = bytearray()
        async for chunk in _iter_stream(stream):
            buffer.extend(chunk)
            while True:
                newline_at = buffer.find(b"\n")
                if newline_at < 0:
                    break
                line = bytes(buffer[:newline_at])
                del buffer[: newline_at + 1]
                yield line.decode(encoding, errors="replace").rstrip("\r")
            if len(buffer) > max_line_bytes:
                raise ValueError(f"{source} line exceeds {max_line_bytes} bytes")
        if buffer:
            yield bytes(buffer).decode(encoding, errors="replace").rstrip("\r")

    async def send_stdin(self, data: bytes | str) -> None:
        """Write to the child's stdin; requires ``stdin=PIPE``."""
        stream = self._process.stdin
        if stream is None:
            raise RuntimeError("process was not opened with stdin=PIPE")
        await stream.send(data.encode("utf-8") if isinstance(data, str) else data)

    async def close_stdin(self) -> None:
        """Close the child's stdin so it observes EOF."""
        stream = self._process.stdin
        if stream is None:
            return
        try:
            await stream.aclose()
        except (anyio.BrokenResourceError, anyio.ClosedResourceError):
            pass

    def terminate(self) -> None:
        """Send the platform's graceful termination signal (SIGTERM on POSIX)."""
        try:
            self._process.terminate()
        except (ProcessLookupError, OSError):
            pass

    def kill(self) -> None:
        """Send an uncatchable kill signal (SIGKILL on POSIX)."""
        try:
            self._process.kill()
        except (ProcessLookupError, OSError):
            pass


async def open_process(
    command: str | Sequence[str],
    *,
    stdin: int | IO[Any] | None = DEVNULL,
    stdout: int | IO[Any] | None = PIPE,
    stderr: int | IO[Any] | None = PIPE,
    cwd: Any = None,
    env: Any = None,
    **kwargs: Any,
) -> Process:
    """Start a child process and return the unified :class:`Process` adapter.

    A ``str`` command runs through the platform shell (``sh -c`` on POSIX); a
    sequence runs the executable directly.  ``stderr=STDOUT`` merges stderr into
    the stdout pipe.  The process is *detached* from the enclosing AnyIO scope,
    so a parent that returns or is cancelled does not implicitly kill it; use
    :func:`terminate_then_kill` for deterministic cleanup.
    """
    process = await anyio.open_process(
        command,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        cwd=cwd,
        env=env,
        **kwargs,
    )
    return Process(process)


async def run_process(
    command: str | Sequence[str],
    *,
    stdin: int | IO[Any] | None = DEVNULL,
    stdout: int | IO[Any] | None = PIPE,
    stderr: int | IO[Any] | None = PIPE,
    cwd: Any = None,
    env: Any = None,
    check: bool = False,
    encoding: str = "utf-8",
) -> ProcessResult:
    """Run a short, non-interactive command to completion.

    Never use this for long-lived or interactive children: output is only
    available after exit.  A cancelled or timed-out caller kills the child
    through AnyIO's own process teardown (AnyIO's ``run_process`` reaps on
    cancellation).
    """
    kwargs: dict[str, Any] = {}
    if env is not None:
        kwargs["env"] = env
    if cwd is not None:
        kwargs["cwd"] = cwd
    completed = await anyio.run_process(
        command,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        check=False,
        **kwargs,
    )
    result = ProcessResult(
        command=completed.args if isinstance(completed.args, str) else tuple(completed.args),
        returncode=int(completed.returncode),
        stdout=(completed.stdout or b"").decode(encoding, errors="replace"),
        stderr=(completed.stderr or b"").decode(encoding, errors="replace"),
    )
    if check and not result.ok:
        raise subprocess.CalledProcessError(
            result.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return result


async def terminate_then_kill(
    process: Process,
    *,
    grace_seconds: float = DEFAULT_TERMINATE_GRACE_SECONDS,
) -> int | None:
    """Escalate terminate -> grace period -> kill -> reap.

    Runs inside a shielded cancel scope so it is safe to call from a ``finally``
    block, a timeout handler or the cancellation handler of the very task being
    torn down: the child is always reaped, so a cancelled parent cannot leave an
    orphan behind.  Idempotent: an already exited process is simply awaited and
    its exit code returned.
    """
    with anyio.CancelScope(shield=True):
        if process.returncode is None:
            process.terminate()
            with anyio.move_on_after(grace_seconds):
                return await process.wait()
            LOGGER.warning(
                "Process %s ignored SIGTERM after %ss; escalating to SIGKILL",
                process.pid,
                grace_seconds,
            )
            process.kill()
            with anyio.move_on_after(grace_seconds):
                return await process.wait()
        return process.returncode


async def _iter_stream(
    stream: anyio.abc.ByteReceiveStream | None,
) -> AsyncIterator[bytes]:
    if stream is None:
        return
    while True:
        try:
            chunk = await stream.receive()
        except (anyio.EndOfStream, anyio.ClosedResourceError, anyio.BrokenResourceError):
            return
        if not chunk:
            return
        yield chunk


async def _drain_stream(
    stream: anyio.abc.ByteReceiveStream | None,
    sink: list[bytes],
) -> None:
    async for chunk in _iter_stream(stream):
        sink.append(chunk)


__all__ = [
    "DEFAULT_MAX_LINE_BYTES",
    "DEFAULT_TERMINATE_GRACE_SECONDS",
    "DEVNULL",
    "INHERIT",
    "PIPE",
    "Process",
    "ProcessResult",
    "STDOUT",
    "open_process",
    "run_process",
    "terminate_then_kill",
]
