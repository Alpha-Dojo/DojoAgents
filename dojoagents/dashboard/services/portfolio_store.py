from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from dojoagents.dashboard.services.file_store_base import _atomic_write_text

MARKETS = ("us", "sh", "hk")
INDEX_FILENAME = "index.json"
STORE_VERSION = 2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_start_date() -> str:
    today = date.today()
    return date(today.year - 1, today.month, today.day).isoformat()


def _default_config() -> dict[str, Any]:
    start = _default_start_date()
    return {
        "start_date": start,
        "cost_date": start,
        "capital_by_market": {"us": 1_000_000.0, "sh": 1_000_000.0, "hk": 1_000_000.0},
    }


class PortfolioStore:
    """Persist portfolios under ~/.dojo/data/portfolio/.

    Layout:
      ~/.dojo/data/portfolio/index.json       — catalog of portfolio ids + list metadata
      ~/.dojo/data/portfolio/{portfolio_id}.json — full portfolio document

    Each portfolio document stores user-editable config and raw holdings. Quote/KPI
    enrichment happens in PortfolioService on read.
    """

    def __init__(self, data_root: Path) -> None:
        self.root = data_root / "portfolio"
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / INDEX_FILENAME
        self._index: dict[str, Any] = {"version": STORE_VERSION, "portfolios": []}
        self._load_sync()

    @staticmethod
    def _portfolio_path(root: Path, portfolio_id: str) -> Path:
        safe = portfolio_id.replace("/", "_").replace("\\", "_")
        return root / f"{safe}.json"

    async def load(self) -> None:
        self._load_sync()

    def _load_sync(self) -> None:
        if self.index_path.is_file():
            try:
                with self.index_path.open(encoding="utf-8") as handle:
                    raw = json.load(handle)
                if isinstance(raw, dict) and isinstance(raw.get("portfolios"), list):
                    self._index = raw
            except (OSError, json.JSONDecodeError):
                self._index = {"version": STORE_VERSION, "portfolios": []}

        self._reconcile_index_from_disk()
        self._save_index()

    def _reconcile_index_from_disk(self) -> None:
        for path in sorted(self.root.glob("*.json")):
            if path.name == INDEX_FILENAME:
                continue
            portfolio_id = path.stem
            payload = self._read_portfolio_file(portfolio_id)
            if not payload:
                continue
            self._upsert_index_row(payload)

    def _save_index(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index["version"] = STORE_VERSION
        content = json.dumps(self._index, ensure_ascii=False, indent=2) + "\n"
        _atomic_write_text(self.index_path, content)

    def _read_portfolio_file(self, portfolio_id: str) -> Optional[dict[str, Any]]:
        path = self._portfolio_path(self.root, portfolio_id)
        if not path.is_file():
            return None
        try:
            with path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None

    def _write_portfolio_file(self, payload: dict[str, Any]) -> None:
        portfolio_id = str(payload["id"])
        path = self._portfolio_path(self.root, portfolio_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        _atomic_write_text(path, content)

    @staticmethod
    def _to_v2(payload: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(payload)
        migrated["version"] = STORE_VERSION
        migrated.setdefault("pinned", False)
        holdings = migrated.get("holdings")
        normalized_holdings: list[dict[str, Any]] = []
        if isinstance(holdings, list):
            for raw in holdings:
                if not isinstance(raw, dict):
                    continue
                holding = dict(raw)
                holding.setdefault("shares_locked", bool(holding.get("manual_shares", False)))
                holding.setdefault("manual_shares", bool(holding["shares_locked"]))
                holding.setdefault("open_date_locked", False)
                holding.setdefault("cost_override", None)
                holding.setdefault("cost_locked", False)
                normalized_holdings.append(holding)
        migrated["holdings"] = normalized_holdings
        return migrated

    def migrate_to_v2(self, *, dry_run: bool = True) -> dict[str, Any]:
        report: dict[str, Any] = {
            "dry_run": dry_run,
            "would_migrate": [],
            "migrated": [],
            "skipped": [],
            "errors": [],
        }
        for path in sorted(self.root.glob("*.json")):
            if path.name == INDEX_FILENAME:
                continue
            portfolio_id = path.stem
            try:
                original = path.read_text(encoding="utf-8")
                payload = json.loads(original)
                if not isinstance(payload, dict):
                    raise ValueError("portfolio document must be an object")
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                report["errors"].append({"id": portfolio_id, "error": str(exc)})
                continue

            portfolio_id = str(payload.get("id") or portfolio_id)
            if int(payload.get("version") or 1) >= STORE_VERSION:
                report["skipped"].append(portfolio_id)
                continue
            report["would_migrate"].append(portfolio_id)
            if dry_run:
                continue

            backup_path = path.with_name(f"{path.name}.v1.bak")
            if not backup_path.exists():
                _atomic_write_text(backup_path, original)
            migrated = self._to_v2(payload)
            self._write_portfolio_file(migrated)
            self._upsert_index_row(migrated)
            report["migrated"].append(portfolio_id)

        if not dry_run:
            self._save_index()
        return report

    def _upsert_index_row(self, payload: dict[str, Any]) -> None:
        rows = self._index.setdefault("portfolios", [])
        portfolio_id = str(payload["id"])
        summary = {
            "id": portfolio_id,
            "name": payload.get("name", portfolio_id),
            "subtitle": payload.get("subtitle"),
            "kind": payload.get("kind", "manual"),
            "pinned": bool(payload.get("pinned", False)),
            "created_at": payload.get("created_at", _utc_now_iso()),
            "updated_at": payload.get("updated_at", _utc_now_iso()),
        }
        for index, row in enumerate(rows):
            if isinstance(row, dict) and row.get("id") == portfolio_id:
                rows[index] = {**row, **summary}
                return
        rows.append(summary)

    def list_index_rows(self) -> List[dict[str, Any]]:
        rows = self._index.get("portfolios", [])
        valid = [row for row in rows if isinstance(row, dict) and row.get("id")]
        return sorted(
            valid,
            key=lambda row: (
                not bool(row.get("pinned", False)),
                str(row.get("name") or "").lower(),
                str(row.get("id")),
            ),
        )

    def get_raw(self, portfolio_id: str) -> Optional[dict[str, Any]]:
        return self._read_portfolio_file(portfolio_id)

    def create(self, name: str) -> dict[str, Any]:
        now = _utc_now_iso()
        portfolio_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "version": STORE_VERSION,
            "id": portfolio_id,
            "name": name.strip(),
            "pinned": False,
            "subtitle": None,
            "kind": "manual",
            "created_at": now,
            "updated_at": now,
            "config": _default_config(),
            "holdings": [],
        }
        self._write_portfolio_file(payload)
        self._upsert_index_row(payload)
        self._save_index()
        return payload

    def update(
        self,
        portfolio_id: str,
        *,
        name: Optional[str] = None,
        pinned: Optional[bool] = None,
        config: Optional[dict[str, Any]] = None,
        shares_by_ticker: Optional[dict[str, float]] = None,
        manual_shares_by_ticker: Optional[dict[str, bool]] = None,
        open_date_by_ticker: Optional[dict[str, Optional[str]]] = None,
        shares_locked_by_ticker: Optional[dict[str, bool]] = None,
        open_date_locked_by_ticker: Optional[dict[str, bool]] = None,
        cost_locked_by_ticker: Optional[dict[str, bool]] = None,
        cost_override_by_ticker: Optional[dict[str, Optional[float]]] = None,
    ) -> Optional[dict[str, Any]]:
        payload = self._read_portfolio_file(portfolio_id)
        if not payload:
            return None

        if name is not None:
            payload["name"] = name.strip()
        if pinned is not None:
            payload["pinned"] = bool(pinned)
        if config is not None:
            payload["config"] = config
        if (
            shares_by_ticker is not None
            or manual_shares_by_ticker is not None
            or open_date_by_ticker is not None
            or shares_locked_by_ticker is not None
            or open_date_locked_by_ticker is not None
            or cost_locked_by_ticker is not None
            or cost_override_by_ticker is not None
        ):
            holdings = payload.setdefault("holdings", [])
            if not isinstance(holdings, list):
                holdings = []
                payload["holdings"] = holdings
            by_ticker = {str(row.get("ticker")): row for row in holdings if isinstance(row, dict) and row.get("ticker")}
            if shares_by_ticker is not None:
                for ticker, shares in shares_by_ticker.items():
                    row = by_ticker.get(ticker)
                    unlock = shares_locked_by_ticker is not None and shares_locked_by_ticker.get(ticker) is False
                    if row is not None and (not bool(row.get("shares_locked", row.get("manual_shares", False))) or unlock):
                        row["shares"] = float(shares)
            if manual_shares_by_ticker is not None:
                for ticker, manual in manual_shares_by_ticker.items():
                    row = by_ticker.get(ticker)
                    if row is not None:
                        row["manual_shares"] = bool(manual)
            if open_date_by_ticker is not None:
                for ticker, open_date in open_date_by_ticker.items():
                    row = by_ticker.get(ticker)
                    if row is None:
                        continue
                    unlock = open_date_locked_by_ticker is not None and open_date_locked_by_ticker.get(ticker) is False
                    if bool(row.get("open_date_locked", False)) and not unlock:
                        continue
                    row.pop("cost_date", None)
                    if open_date is None or not str(open_date).strip():
                        row.pop("open_date", None)
                    else:
                        row["open_date"] = str(open_date).strip()[:10]
            if shares_locked_by_ticker is not None:
                for ticker, locked in shares_locked_by_ticker.items():
                    row = by_ticker.get(ticker)
                    if row is not None:
                        row["shares_locked"] = bool(locked)
                        row["manual_shares"] = bool(locked)
            if open_date_locked_by_ticker is not None:
                for ticker, locked in open_date_locked_by_ticker.items():
                    row = by_ticker.get(ticker)
                    if row is not None:
                        row["open_date_locked"] = bool(locked)
            if cost_override_by_ticker is not None:
                for ticker, cost in cost_override_by_ticker.items():
                    row = by_ticker.get(ticker)
                    unlock = cost_locked_by_ticker is not None and cost_locked_by_ticker.get(ticker) is False
                    if row is not None and (not bool(row.get("cost_locked", False)) or unlock):
                        row["cost_override"] = float(cost) if cost is not None else None
            if cost_locked_by_ticker is not None:
                for ticker, locked in cost_locked_by_ticker.items():
                    row = by_ticker.get(ticker)
                    if row is not None:
                        row["cost_locked"] = bool(locked)
            payload["holdings"] = list(by_ticker.values())

        payload["updated_at"] = _utc_now_iso()
        self._write_portfolio_file(payload)
        self._upsert_index_row(payload)
        self._save_index()
        return payload

    def apply_market_shares(
        self,
        portfolio_id: str,
        shares_by_ticker: dict[str, float],
        *,
        reset_manual: bool = True,
    ) -> Optional[dict[str, Any]]:
        payload = self._read_portfolio_file(portfolio_id)
        if not payload:
            return None

        holdings = payload.setdefault("holdings", [])
        if not isinstance(holdings, list):
            holdings = []
            payload["holdings"] = holdings

        for row in holdings:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "")
            if ticker not in shares_by_ticker:
                continue
            row["shares"] = float(shares_by_ticker[ticker])
            if reset_manual:
                row["manual_shares"] = False

        payload["updated_at"] = _utc_now_iso()
        self._write_portfolio_file(payload)
        self._upsert_index_row(payload)
        self._save_index()
        return payload

    def delete(self, portfolio_id: str) -> bool:
        path = self._portfolio_path(self.root, portfolio_id)
        existed = path.is_file()
        if existed:
            path.unlink(missing_ok=True)
        rows = self._index.setdefault("portfolios", [])
        self._index["portfolios"] = [row for row in rows if not (isinstance(row, dict) and row.get("id") == portfolio_id)]
        self._save_index()
        return existed

    def add_holding(
        self,
        portfolio_id: str,
        *,
        ticker: str,
        market: str,
        shares: float = 0.0,
    ) -> Optional[dict[str, Any]]:
        payload = self._read_portfolio_file(portfolio_id)
        if not payload:
            return None

        holdings = payload.setdefault("holdings", [])
        if not isinstance(holdings, list):
            holdings = []
            payload["holdings"] = holdings

        normalized_ticker = ticker.strip()
        for row in holdings:
            if not isinstance(row, dict):
                continue
            if str(row.get("ticker")) == normalized_ticker and str(row.get("market")) == market:
                if shares > 0:
                    row["shares"] = shares
                payload["updated_at"] = _utc_now_iso()
                self._write_portfolio_file(payload)
                self._upsert_index_row(payload)
                self._save_index()
                return payload

        holdings.append(
            {
                "ticker": normalized_ticker,
                "market": market,
                "shares": float(shares),
                "manual_shares": False,
                "shares_locked": False,
                "open_date_locked": False,
                "cost_override": None,
                "cost_locked": False,
                "added_at": _utc_now_iso(),
            }
        )
        payload["updated_at"] = _utc_now_iso()
        self._write_portfolio_file(payload)
        self._upsert_index_row(payload)
        self._save_index()
        return payload

    def remove_holding(
        self,
        portfolio_id: str,
        *,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        payload = self._read_portfolio_file(portfolio_id)
        if not payload:
            return None

        holdings = payload.setdefault("holdings", [])
        if not isinstance(holdings, list):
            holdings = []
            payload["holdings"] = holdings

        target_ticker = ticker.strip()
        before = len(holdings)
        payload["holdings"] = [
            row for row in holdings if not (isinstance(row, dict) and str(row.get("ticker")) == target_ticker and (market is None or str(row.get("market")) == market))
        ]
        if len(payload["holdings"]) == before:
            return None

        payload["updated_at"] = _utc_now_iso()
        self._write_portfolio_file(payload)
        self._upsert_index_row(payload)
        self._save_index()
        return payload

    def stats(self) -> dict[str, int]:
        return {"total": len(self.list_index_rows())}
