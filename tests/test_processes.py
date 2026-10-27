"""S6 acceptance tests for the unified child-process adapter."""

import os
import signal
import subprocess
import time

import anyio
import pytest

from dojoagents.tools import processes
from dojoagents.utils.detached_tasks import drain_detached, pending_detached, start_detached


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _force_kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# 短命令：run_process
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_run_process_propagates_nonzero_exit_code():
    result = await processes.run_process(["sh", "-c", "echo out; echo err 1>&2; exit 7"])

    assert result.returncode == 7
    assert result.ok is False
    assert result.stdout == "out\n"
    assert result.stderr == "err\n"


@pytest.mark.asyncio
async def test_run_process_check_raises_called_process_error():
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        await processes.run_process(["sh", "-c", "exit 3"], check=True)

    assert excinfo.value.returncode == 3


# --------------------------------------------------------------------------- #
# 流式进程：open_process
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_open_process_stdin_stdout_stderr():
    env = dict(os.environ)
    env["PROBE_TAG"] = "shell-env"

    process = await processes.open_process(
        "cat; echo $PROBE_TAG; echo merged 1>&2",
        stdin=processes.PIPE,
        stdout=processes.PIPE,
        stderr=processes.STDOUT,
        env=env,
    )
    await process.send_stdin("typed\n")
    await process.close_stdin()

    stdout, stderr = await process.communicate()

    assert process.pid > 0
    assert process.returncode == 0
    assert stdout == b"typed\nshell-env\nmerged\n"
    # stderr=STDOUT 时没有独立的 stderr 管道
    assert stderr == b""


@pytest.mark.asyncio
async def test_open_process_keeps_stderr_separate():
    process = await processes.open_process(
        ["sh", "-c", "echo out; echo err 1>&2; exit 5"],
        stdout=processes.PIPE,
        stderr=processes.PIPE,
    )

    stdout, stderr = await process.communicate()

    assert stdout == b"out\n"
    assert stderr == b"err\n"
    assert process.returncode == 5


@pytest.mark.asyncio
async def test_open_process_communicate_feeds_stdin():
    process = await processes.open_process(
        ["cat"],
        stdin=processes.PIPE,
        stdout=processes.PIPE,
        stderr=processes.DEVNULL,
    )

    stdout, _ = await process.communicate("piped-in\n")

    assert stdout == b"piped-in\n"
    assert process.returncode == 0


@pytest.mark.asyncio
async def test_iter_lines_decodes_lines():
    process = await processes.open_process(
        ["sh", "-c", "printf 'a\\nb\\nc\\n'"],
        stdout=processes.PIPE,
        stderr=processes.DEVNULL,
    )

    lines = [line async for line in process.iter_lines()]

    assert lines == ["a", "b", "c"]
    assert await process.wait() == 0


@pytest.mark.asyncio
async def test_iter_lines_rejects_unknown_source():
    process = await processes.open_process(["true"], stdout=processes.PIPE, stderr=processes.PIPE)
    try:
        with pytest.raises(ValueError):
            async for _line in process.iter_lines(source="stderr2"):
                pass
    finally:
        await process.wait()


# --------------------------------------------------------------------------- #
# 取消 / 超时清理：terminate -> grace -> kill -> reap
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_terminate_then_kill_terminates_and_reaps():
    process = await processes.open_process(["sleep", "30"], stdout=processes.DEVNULL, stderr=processes.DEVNULL)
    pid = process.pid

    returncode = await processes.terminate_then_kill(process, grace_seconds=2.0)

    assert returncode == -signal.SIGTERM
    assert process.returncode is not None
    assert _is_alive(pid) is False


@pytest.mark.asyncio
async def test_terminate_then_kill_escalates_when_sigterm_is_ignored():
    process = await processes.open_process(
        ["sh", "-c", "trap '' TERM; sleep 30"],
        stdout=processes.DEVNULL,
        stderr=processes.DEVNULL,
    )
    pid = process.pid
    await anyio.sleep(0.3)  # 等 trap 安装完成

    started = time.perf_counter()
    returncode = await processes.terminate_then_kill(process, grace_seconds=0.5)
    elapsed = time.perf_counter() - started

    assert returncode == -signal.SIGKILL
    assert _is_alive(pid) is False
    # 必须真的等过 grace period，而不是立刻 SIGKILL
    assert elapsed >= 0.4


@pytest.mark.asyncio
async def test_terminate_then_kill_is_idempotent():
    process = await processes.open_process(["sh", "-c", "exit 4"], stdout=processes.DEVNULL, stderr=processes.DEVNULL)
    await process.wait()

    assert await processes.terminate_then_kill(process) == 4
    assert await processes.terminate_then_kill(process) == 4


@pytest.mark.asyncio
async def test_terminate_then_kill_reaps_when_parent_is_cancelled():
    """父任务被取消后不得留下孤儿进程。"""
    captured: dict[str, object] = {}

    async def parent() -> None:
        child = await processes.open_process(["sleep", "30"], stdout=processes.DEVNULL, stderr=processes.DEVNULL)
        captured["pid"] = child.pid
        try:
            await anyio.sleep_forever()
        finally:
            captured["returncode"] = await processes.terminate_then_kill(child, grace_seconds=1.0)

    with anyio.move_on_after(0.2):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(parent)

    assert captured["returncode"] == -signal.SIGTERM
    assert _is_alive(int(captured["pid"])) is False


@pytest.mark.asyncio
async def test_run_process_timeout_reaps_child(tmp_path):
    pid_file = tmp_path / "child.pid"

    async def run_with_timeout() -> None:
        with pytest.raises(TimeoutError):
            with anyio.fail_after(0.3):
                await processes.run_process(
                    ["sh", "-c", f"echo $$ > {pid_file}; sleep 30"],
                )

    await run_with_timeout()
    await anyio.sleep(0.3)

    child_pid = int(pid_file.read_text().strip())
    alive = _is_alive(child_pid)
    if alive:
        _force_kill(child_pid)
    assert alive is False


@pytest.mark.asyncio
async def test_open_process_outlives_enclosing_cancel_scope():
    """open_process 不与所在取消作用域绑定：清理必须显式进行。

    这是后台进程能在工具调用返回后继续运行的前提，也是本设计选择
    ``terminate_then_kill`` 负责显式回收的原因。
    """
    captured: dict[str, int] = {}

    async def spawner() -> None:
        child = await processes.open_process(["sleep", "30"], stdout=processes.DEVNULL, stderr=processes.DEVNULL)
        captured["pid"] = child.pid

    with anyio.move_on_after(0.1):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(spawner)

    try:
        assert _is_alive(captured["pid"]) is True
    finally:
        _force_kill(captured["pid"])


# --------------------------------------------------------------------------- #
# detached task 边界
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_start_detached_survives_its_creator_scope():
    completed: list[str] = []

    async def worker() -> None:
        await anyio.sleep(0.1)
        completed.append("done")

    async def creator() -> None:
        start_detached(worker(), name="test-detached")

    with anyio.move_on_after(0.02):
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(creator)

    assert pending_detached() == 1
    await drain_detached(timeout=2.0)
    assert completed == ["done"]
    assert pending_detached() == 0
