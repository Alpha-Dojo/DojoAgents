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
