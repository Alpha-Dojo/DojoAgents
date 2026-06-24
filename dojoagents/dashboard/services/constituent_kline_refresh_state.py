import json
import logging
from pathlib import Path
import datetime

logger = logging.getLogger(__name__)


class RefreshStateStore:
    def __init__(self, runtime_dir: Path):
        self.file_path = runtime_dir / "refresh_state.json"

    def _read(self) -> dict:
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read refresh state from {self.file_path}: {e}")
            return {}

    def _write(self, data: dict):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.file_path.with_suffix(".tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self.file_path)
        except Exception as e:
            logger.error(f"Failed to write refresh state to {self.file_path}: {e}")
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

    def get_last_refresh_date(self, market_group: str) -> datetime.date | None:
        data = self._read()
        date_str = data.get(market_group)
        if not date_str:
            return None
        try:
            return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

    def set_last_refresh_date(self, market_group: str, date: datetime.date):
        data = self._read()
        data[market_group] = date.strftime("%Y-%m-%d")
        data[f"{market_group}_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._write(data)

    async def get_last_refresh_date_async(self, market_group: str) -> datetime.date | None:
        return self.get_last_refresh_date(market_group)

    async def set_last_refresh_date_async(self, market_group: str, date: datetime.date) -> None:
        self.set_last_refresh_date(market_group, date)
