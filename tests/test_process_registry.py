import anyio
import pytest
import asyncio
from dojoagents.tools.process_registry import AsyncProcessRegistry

@pytest.mark.asyncio
async def test_process_registry_spawn_and_await():
    registry = AsyncProcessRegistry()
    # 异步启动后台命令，休眠 1 秒
    proc_session = await registry.spawn("sleep 1")
    assert proc_session.id is not None
    
    # 轮询验证后台进程处于活跃状态
    assert registry.has_active_processes()
    
    # 等待该进程执行结束
    await proc_session.wait()
    # 给收割协程一个微小的运行时间片
    await asyncio.sleep(0.1)
    assert not registry.has_active_processes()

@pytest.mark.asyncio
async def test_process_registry_cleanup():
    from dojoagents.tools.process_registry import process_registry
    # 启动一个超长挂起的进程
    proc_session = await process_registry.spawn("sleep 100")
    assert process_registry.has_active_processes()
    
    # 强制清理
    process_registry.cleanup()
    assert not process_registry.has_active_processes()


@pytest.mark.asyncio
async def test_process_registry_prunes_exited_processes_without_waiting_for_reaper():
    """退出进程必须立即从注册表消失，不能残留。"""

    registry = AsyncProcessRegistry()
    proc_session = await registry.spawn("sh -c 'exit 0'")
    await proc_session.wait()

    assert registry.has_active_processes() is False
    assert registry.processes == {}


@pytest.mark.asyncio
async def test_background_process_emits_completion_event_with_output():
    """后台进程退出后按 session_key 投递带完整输出的完成事件。"""

    registry = AsyncProcessRegistry()
    session = await registry.spawn("printf 'line1\\nline2\\n'")
    session.session_key = "cli:test_target:user123"
    session.notify_on_complete = True

    with anyio.fail_after(10.0):
        event = await registry.completion_events.receive()

    assert event["type"] == "completion"
    assert event["session_id"] == session.id
    assert event["session_key"] == "cli:test_target:user123"
    assert event["command"] == "printf 'line1\\nline2\\n'"
    assert event["exit_code"] == 0
    assert event["output"] == "line1\nline2\n"
    assert registry.has_active_processes() is False


@pytest.mark.asyncio
async def test_background_process_completion_event_propagates_nonzero_exit_code():
    registry = AsyncProcessRegistry()
    session = await registry.spawn("sh -c 'echo boom; exit 9'")
    session.notify_on_complete = True

    with anyio.fail_after(10.0):
        event = await registry.completion_events.receive()

    assert event["exit_code"] == 9
    assert "boom" in event["output"]


@pytest.mark.asyncio
async def test_background_process_terminate_deregisters_session():
    registry = AsyncProcessRegistry()
    session = await registry.spawn("sleep 30")
    assert registry.has_active_processes() is True

    session.terminate()
    await session.wait()
    with anyio.fail_after(10.0):
        while registry.has_active_processes():
            await anyio.sleep(0.05)

    assert registry.processes == {}
