import anyio
import pytest
from unittest.mock import AsyncMock, patch

from dojoagents.tools import processes
from dojoagents.tools.environments.docker import DockerEnvironment
from dojoagents.tools.environments.modal import ModalEnvironment
from dojoagents.tools.environments.ssh import SSHEnvironment


class _StubProcess:
    """Stand-in for :class:`dojoagents.tools.processes.Process`.

    Only the surface the environments actually use is implemented, so the mock
    path keeps exercising the same call sequence as the real adapter without
    pretending to be an ``asyncio`` subprocess.
    """

    def __init__(self, stdout: bytes = b"", returncode: int = 0, pid: int = 4242) -> None:
        self._stdout = stdout
        self._returncode = returncode
        self.pid = pid
        self.terminated = False
        self.killed = False

    @property
    def returncode(self) -> int:
        return self._returncode

    async def wait(self) -> int:
        return self._returncode

    async def communicate(self, input=None) -> tuple[bytes, bytes]:
        return self._stdout, b""

    def terminate(self) -> None:
        self.terminated = True
        self._returncode = -15

    def kill(self) -> None:
        self.killed = True
        self._returncode = -9


def _patched_processes(stdout: bytes = b"", returncode: int = 0):
    """Patch the unified process adapter used by every environment."""

    stub = _StubProcess(stdout=stdout, returncode=returncode)
    open_process = AsyncMock(return_value=stub)
    run_process = AsyncMock(return_value=processes.ProcessResult(command=("docker",), returncode=0, stdout="", stderr=""))
    return stub, open_process, run_process


@pytest.mark.asyncio
async def test_docker_env_run_bash_calls_process_adapter():
    env = DockerEnvironment(image="python:3.11", cwd="/workspace")

    stub, open_process, run_process = _patched_processes(
        stdout=b"__DOJO_CWD_xyz__/workspace__DOJO_CWD_xyz__",
    )

    with patch("dojoagents.tools.processes.open_process", new=open_process), patch(
        "dojoagents.tools.processes.run_process", new=run_process
    ):
        res = await env.execute("ls")

    assert res["exit_code"] == 0

    # 两次进程操作：第一次拉起容器（短命令），第二次执行指令（长驻/流式）
    assert run_process.await_count == 1
    assert open_process.await_count == 1

    # 第一次调用是 docker run 且包含 -v 挂载
    run_args = list(run_process.await_args.args[0])
    assert run_args[0] == "docker"
    assert run_args[1] == "run"
    assert "-v" in run_args
    assert env.container_name in run_args

    # 第二次调用是 docker exec
    exec_args = list(open_process.await_args.args[0])
    assert exec_args[0] == "docker"
    assert exec_args[1] == "exec"
    assert env.container_name in exec_args
    assert stub.killed is False


@pytest.mark.asyncio
async def test_ssh_env_run_bash_calls_process_adapter():
    env = SSHEnvironment(host="127.0.0.1", user="testuser", port=22, cwd="/home/testuser")

    _, open_process, _ = _patched_processes(
        stdout=b"__DOJO_CWD_xyz__/home/testuser__DOJO_CWD_xyz__",
    )

    with patch("dojoagents.tools.processes.open_process", new=open_process):
        res = await env.execute("ls")

    assert res["exit_code"] == 0
    assert open_process.await_count == 1
    args = list(open_process.await_args.args[0])
    assert "ssh" in args[0]
    assert args[3] == "testuser@127.0.0.1"
    # stderr 合并进 stdout，stdin 走 DEVNULL（未提供 stdin_data）
    assert open_process.await_args.kwargs["stderr"] == processes.STDOUT
    assert open_process.await_args.kwargs["stdin"] == processes.DEVNULL


@pytest.mark.asyncio
async def test_modal_env_run_bash_calls_process_adapter():
    env = ModalEnvironment(image="python:3.11", cwd="/root")

    _, open_process, _ = _patched_processes()

    with patch("dojoagents.tools.processes.open_process", new=open_process):
        res = await env.execute("ls")

    assert res["exit_code"] == 0
    args = list(open_process.await_args.args[0])
    assert args[:5] == ["modal", "sandbox", "run", "--image", "python:3.11"]
    assert args[5:7] == ["bash", "-c"]


@pytest.mark.asyncio
async def test_environment_timeout_reaps_child():
    """超时路径必须回收子进程（terminate → grace → kill）。"""
    env = SSHEnvironment(host="127.0.0.1", user="testuser", port=22, cwd="/home/testuser")
    stub = _StubProcess()

    async def _never_finishes(input=None):
        await anyio.sleep_forever()

    stub.communicate = _never_finishes  # type: ignore[assignment]
    open_process = AsyncMock(return_value=stub)

    reaped = {"count": 0}

    async def _pseudo_terminate_then_kill(process, *, grace_seconds=None):
        reaped["count"] += 1
        process.kill()
        return process.returncode

    with patch("dojoagents.tools.processes.open_process", new=open_process), patch(
        "dojoagents.tools.processes.terminate_then_kill", new=_pseudo_terminate_then_kill
    ):
        res = await env.execute("ls", timeout=0.05)

    assert res == {"output": "Command timed out", "exit_code": 124}
    assert reaped["count"] == 1
    assert stub.killed is True
