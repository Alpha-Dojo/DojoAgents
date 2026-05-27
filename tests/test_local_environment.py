import asyncio
import pytest
import tempfile
import os
from dojoagents.tools.environments.local import LocalEnvironment
from dojoagents.tools.sandbox import SandboxPolicy

@pytest.mark.asyncio
async def test_local_env_execute_success():
    policy = SandboxPolicy()
    env = LocalEnvironment(policy=policy, cwd=tempfile.gettempdir())
    
    res = await env.execute("echo 'hello dojo'")
    assert res["exit_code"] == 0
    assert "hello dojo" in res["output"]

@pytest.mark.asyncio
async def test_local_env_cwd_persistence():
    policy = SandboxPolicy()
    tmp_dir1 = tempfile.mkdtemp()
    tmp_dir2 = tempfile.mkdtemp()
    try:
        env = LocalEnvironment(policy=policy, cwd=tmp_dir1)
        # 执行 cd 切换路径
        res = await env.execute(f"cd {tmp_dir2}")
        assert res["exit_code"] == 0
        # 验证执行器的内部 cwd 已更新
        assert env.cwd == os.path.realpath(tmp_dir2)
    finally:
        try:
            os.rmdir(tmp_dir1)
        except OSError:
            pass
        try:
            os.rmdir(tmp_dir2)
        except OSError:
            pass

@pytest.mark.asyncio
async def test_local_env_redaction():
    policy = SandboxPolicy()
    env = LocalEnvironment(policy=policy, cwd=tempfile.gettempdir())
    
    # 验证含有 API Key 的命令输出被自动脱敏
    res = await env.execute("echo 'my key is sk-ant-abcdef1234567890'")
    assert "sk-ant-abcdef1234567890" not in res["output"]
    assert "..." in res["output"]

