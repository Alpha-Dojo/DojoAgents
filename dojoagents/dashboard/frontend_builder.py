import fcntl
import shutil
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_frontend_static_files(source_dir: Path, target_dir: Path) -> None:
    """Checks and automatically builds the frontend project into the target directory."""
    index_file = target_dir / "index.html"

    # Fast path check without lock
    if target_dir.exists() and index_file.exists():
        logger.info(f"Frontend static resources already exist in {target_dir}. Skipping build.")
        return

    # Ensure source dir exists
    if not source_dir.exists():
        logger.warning(f"Frontend source directory {source_dir} not found. Cannot build frontend.")
        return

    # To handle multi-process concurrency (e.g. gunicorn/uvicorn workers)
    lock_file = source_dir / ".build.lock"

    with open(lock_file, "w") as f:
        try:
            # Acquire exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)

            # Double check inside the lock
            if target_dir.exists() and index_file.exists():
                logger.info(f"Frontend static resources already exist in {target_dir}. Skipping build.")
                return

            logger.info("No frontend build found. Preparing to compile and package...")

            npm_path = shutil.which("npm")
            if not npm_path:
                yarn_path = shutil.which("yarn")
                if yarn_path:
                    logger.info("npm not found, falling back to yarn.")
                    npm_path = yarn_path
                else:
                    raise RuntimeError("Could not find npm or yarn. Please install Node.js or provide the pre-built files manually.")

            # Install dependencies
            logger.info(f"Installing frontend dependencies using {npm_path}...")
            try:
                subprocess.run([npm_path, "install"], cwd=source_dir, check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to install frontend dependencies: {e}")

            # Build project
            logger.info(f"Building frontend project using {npm_path}...")
            try:
                subprocess.run([npm_path, "run", "build"], cwd=source_dir, check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to build frontend project: {e}")

            # Move to target dir if needed
            default_dist = source_dir / "dist"
            if default_dist.resolve() != target_dir.resolve():
                logger.info(f"Moving build artifacts from {default_dist} to {target_dir}...")
                if target_dir.exists():
                    shutil.rmtree(target_dir)

                # Make sure parent directory of target_dir exists
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(default_dist, target_dir)
                shutil.rmtree(default_dist)

            logger.info("Frontend build and deployment completed successfully.")

        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
