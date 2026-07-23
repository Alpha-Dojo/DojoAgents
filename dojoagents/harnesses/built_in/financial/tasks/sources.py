from pathlib import Path

from dojoagents.tools.session_file_tool import (
    get_read_session_output_spec,
    get_write_session_file_spec,
)
from dojoagents.tools.session_input_tool import get_read_session_input_spec

TASK_IO_TOOL_NAMES = (
    "read_session_input",
    "read_session_output",
    "write_session_file",
)


def financial_task_directories() -> tuple[Path, ...]:
    return (Path(__file__).resolve().parent / "definitions",)


def get_task_io_specs(runtime):
    service = runtime.session_state_facade.service
    compatibility_root = service.config.root
    return (
        get_read_session_input_spec(compatibility_root, session_service=service),
        get_read_session_output_spec(compatibility_root, session_service=service),
        get_write_session_file_spec(compatibility_root, session_service=service),
    )


__all__ = ["TASK_IO_TOOL_NAMES", "financial_task_directories", "get_task_io_specs"]
