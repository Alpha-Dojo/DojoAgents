from __future__ import annotations

import shutil
import stat
from pathlib import Path


class UnsafeGeneratedMemoryPathError(ValueError):
    """Raised when a configured generated-memory directory is unsafe to clear."""


class GeneratedMemoryService:
    def __init__(self, generated_skill_dir: str | Path) -> None:
        self.generated_skill_dir = Path(generated_skill_dir).expanduser()

    def clear(self) -> tuple[Path, int]:
        target = self.generated_skill_dir
        self._validate_target(target)

        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            return target.resolve(), 0
        if target.is_symlink() or not target.is_dir():
            raise UnsafeGeneratedMemoryPathError(
                f"Generated memory path must be a real directory: {target}"
            )

        self._make_owner_writable(target)
        deleted_count = 0
        for child in target.iterdir():
            if child.is_symlink() or not child.is_dir():
                child.unlink()
            else:
                shutil.rmtree(child, onexc=self._force_remove)
            deleted_count += 1

        remaining = list(target.iterdir())
        if remaining:
            names = ", ".join(path.name for path in remaining)
            raise OSError(f"Generated memory directory is not empty after deletion: {names}")
        return target.resolve(), deleted_count

    @staticmethod
    def _make_owner_writable(path: Path) -> None:
        mode = path.stat().st_mode
        required = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        if mode & required != required:
            path.chmod(mode | required)

    @classmethod
    def _force_remove(cls, function, path: str, _excinfo) -> None:
        target = Path(path)
        cls._make_owner_writable(target)
        function(path)

    @staticmethod
    def _validate_target(target: Path) -> None:
        absolute = target.absolute()
        home = Path.home().absolute()
        if absolute == Path(absolute.anchor) or absolute == home:
            raise UnsafeGeneratedMemoryPathError(
                f"Refusing to clear unsafe generated memory path: {target}"
            )
