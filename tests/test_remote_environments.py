import pytest
from unittest.mock import AsyncMock, patch
from dojoagents.tools.environments.docker import DockerEnvironment
from dojoagents.tools.environments.ssh import SSHEnvironment

@pytest.mark.asyncio
async def test_docker_env_run_bash_calls_subprocess():
    env = DockerEnvironment(image="python:3.11", cwd="/workspace")
    
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"__DOJO_CWD_xyz__/workspace__DOJO_CWD_xyz__", b"")
    mock_process.returncode = 0
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        res = await env.execute("ls")
        assert res["exit_code"] == 0
        
        # 应该被调用了两次：第一次创建容器，第二次执行指令
        assert mock_exec.call_count == 2
        
        # 验证第一次调用是 docker run 且包含 -v 挂载
        run_args = mock_exec.call_args_list[0][0]
        assert "run" in run_args[1]
        assert "-v" in run_args
        
        # 验证第二次调用是 docker exec
        exec_args = mock_exec.call_args_list[1][0]
        assert "exec" in exec_args[1]
        assert env.container_name in exec_args[3]

@pytest.mark.asyncio
async def test_ssh_env_run_bash_calls_subprocess():
    env = SSHEnvironment(host="127.0.0.1", user="testuser", port=22, cwd="/home/testuser")
    
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"__DOJO_CWD_xyz__/home/testuser__DOJO_CWD_xyz__", b"")
    mock_process.returncode = 0
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
        res = await env.execute("ls")
        assert res["exit_code"] == 0
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert "ssh" in args[0]
        assert "testuser@127.0.0.1" in args[3]
