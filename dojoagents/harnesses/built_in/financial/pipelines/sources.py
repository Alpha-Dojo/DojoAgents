from pathlib import Path


def financial_pipeline_directories() -> tuple[Path, ...]:
    return (Path(__file__).resolve().parent / "definitions",)


__all__ = ["financial_pipeline_directories"]
