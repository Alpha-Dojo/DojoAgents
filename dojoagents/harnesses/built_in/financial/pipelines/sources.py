from pathlib import Path


def financial_pipeline_directories() -> tuple[Path, ...]:
    compatibility_root = Path(__file__).resolve().parents[4] / "tasks" / "pipelines"
    return (compatibility_root,)


__all__ = ["financial_pipeline_directories"]
