from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from dojoagents.sessions.atomic import _atomic_write_text
from dojoagents.logging import LOGGER

MARKETS = ("us", "sh", "hk")
INDEX_FILENAME = "index.json"
STORE_VERSION = 3
V2_VERSION = 2


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


DEFAULT_PORTFOLIO_START_DATE = "2025-01-02"


def _default_start_date() -> str:
    return DEFAULT_PORTFOLIO_START_DATE


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

        # Check if the store points to ~/.dojo/data/portfolio and has no portfolio data
        default_portfolio_path = Path("~/.dojo/data/portfolio").expanduser().resolve()
        try:
            is_default = self.root.resolve() == default_portfolio_path
        except Exception:
            is_default = False

        import os

        if is_default or os.environ.get("_FORCE_COPY_DEFAULTS") == "1":
            # Check if there are any portfolio JSON files (excluding index.json)
            has_data = False
            if self.root.exists():
                try:
                    if any(p.name != INDEX_FILENAME for p in self.root.glob("*.json")):
                        has_data = True
                except Exception:
                    pass
            if not has_data:
                self._copy_default_portfolios()

        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / INDEX_FILENAME
        self._index: dict[str, Any] = {"version": STORE_VERSION, "portfolios": []}
        self._portfolio_locks: dict[str, threading.Lock] = {}
        self._portfolio_locks_guard = threading.Lock()
        self._load_sync()

    def _lock_for(self, portfolio_id: str) -> threading.Lock:
        with self._portfolio_locks_guard:
            lock = self._portfolio_locks.get(portfolio_id)
            if lock is None:
                lock = threading.Lock()
                self._portfolio_locks[portfolio_id] = lock
            return lock

    def _copy_default_portfolios(self) -> None:
        import shutil

        default_dir = Path(__file__).resolve().parent.parent / "data" / "default_portfolios"
        if not default_dir.exists():
            default_dir = Path(__file__).resolve().parent.parent / "data" / "default_portfolio"

        if default_dir.exists() and default_dir.is_dir():
            LOGGER.info(f"Copying default portfolios from {default_dir} to {self.root}")
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                for file_path in default_dir.glob("*"):
                    if file_path.is_file():
                        shutil.copy(file_path, self.root / file_path.name)
            except Exception as e:
                LOGGER.exception(f"Failed to copy default portfolios from {default_dir} to {self.root}: {e}")
        else:
            LOGGER.warning(f"Default portfolios directory not found at {default_dir}")

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
        if not isinstance(raw, dict):
            return None
        return self._normalize_document(raw)

    def _write_portfolio_file(self, payload: dict[str, Any]) -> None:
        payload = self._normalize_document(dict(payload))
        portfolio_id = str(payload["id"])
        path = self._portfolio_path(self.root, portfolio_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        _atomic_write_text(path, content)

    @staticmethod
    def _normalize_document(payload: dict[str, Any]) -> dict[str, Any]:
        version = int(payload.get("version") or 1)
        if version < V2_VERSION:
            return payload

        normalized_holdings: list[dict[str, Any]] = []
        for raw in payload.get("holdings") or []:
            if not isinstance(raw, dict) or not raw.get("ticker"):
                continue
            holding = dict(raw)
            holding.setdefault(
                "shares_locked",
                bool(holding.get("manual_shares", False)),
            )
            holding.setdefault(
                "manual_shares",
                bool(holding["shares_locked"]),
            )
            holding.setdefault("open_date_locked", False)
            holding.setdefault("cost_override", None)
            holding.setdefault("cost_locked", False)
            normalized_holdings.append(holding)
        payload["holdings"] = normalized_holdings
        if "candidates" not in payload:
            payload["candidates"] = [
                {
                    "ticker": str(holding["ticker"]),
                    "market": str(holding.get("market") or ""),
                    "added_at": holding.get("added_at") or _utc_now_iso(),
                }
                for holding in normalized_holdings
            ]
        payload.setdefault("orders", [])
        payload["version"] = STORE_VERSION
        return payload

    @staticmethod
    def _to_v2(payload: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(payload)
        migrated["version"] = V2_VERSION
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
            if int(payload.get("version") or 1) >= V2_VERSION:
                report["skipped"].append(portfolio_id)
                continue
            report["would_migrate"].append(portfolio_id)
            if dry_run:
                continue

            backup_path = path.with_name(f"{path.name}.v1.bak")
            if not backup_path.exists():
                _atomic_write_text(backup_path, original)
            migrated = self._to_v2(payload)
            content = json.dumps(migrated, ensure_ascii=False, indent=2) + "\n"
            _atomic_write_text(path, content)
            self._upsert_index_row(migrated)
            report["migrated"].append(portfolio_id)

        if not dry_run:
            self._index["version"] = V2_VERSION
            _atomic_write_text(
                self.index_path,
                json.dumps(
                    self._index,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
            )
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

    def create(self, name: str, *, kind: str = "manual") -> dict[str, Any]:
        now = _utc_now_iso()
        portfolio_id = str(uuid.uuid4())
        normalized_kind = "agent" if kind == "agent" else "manual"
        payload: dict[str, Any] = {
            "version": STORE_VERSION,
            "id": portfolio_id,
            "name": name.strip(),
            "pinned": False,
            "subtitle": None,
            "kind": normalized_kind,
            "created_at": now,
            "updated_at": now,
            "config": _default_config(),
            "holdings": [],
            "candidates": [],
            "orders": [],
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
        kind: Optional[str] = None,
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
        if kind is not None:
            payload["kind"] = "agent" if kind == "agent" else "manual"
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
            for holding in payload.get("holdings") or []:
                if not isinstance(holding, dict):
                    continue
                ticker = str(holding.get("ticker") or "")
                shares_was_locked = bool(holding.get("shares_locked"))
                open_date_was_locked = bool(holding.get("open_date_locked"))
                cost_was_locked = bool(holding.get("cost_locked"))
                if shares_locked_by_ticker is not None and ticker in shares_locked_by_ticker:
                    holding["shares_locked"] = bool(shares_locked_by_ticker[ticker])
                    holding["manual_shares"] = holding["shares_locked"]
                if open_date_locked_by_ticker is not None and ticker in open_date_locked_by_ticker:
                    holding["open_date_locked"] = bool(open_date_locked_by_ticker[ticker])
                if cost_locked_by_ticker is not None and ticker in cost_locked_by_ticker:
                    holding["cost_locked"] = bool(cost_locked_by_ticker[ticker])
                if (
                    shares_by_ticker is not None
                    and ticker in shares_by_ticker
                    and (not shares_was_locked or (shares_locked_by_ticker is not None and shares_locked_by_ticker.get(ticker) is False))
                ):
                    holding["shares"] = float(shares_by_ticker[ticker])
                if manual_shares_by_ticker is not None and ticker in manual_shares_by_ticker:
                    holding["manual_shares"] = bool(manual_shares_by_ticker[ticker])
                if (
                    open_date_by_ticker is not None
                    and ticker in open_date_by_ticker
                    and (not open_date_was_locked or (open_date_locked_by_ticker is not None and open_date_locked_by_ticker.get(ticker) is False))
                ):
                    holding["open_date"] = open_date_by_ticker[ticker]
                if (
                    cost_override_by_ticker is not None
                    and ticker in cost_override_by_ticker
                    and (not cost_was_locked or (cost_locked_by_ticker is not None and cost_locked_by_ticker.get(ticker) is False))
                ):
                    holding["cost_override"] = cost_override_by_ticker[ticker]

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
        for holding in payload.get("holdings") or []:
            ticker = str(holding.get("ticker") or "")
            if ticker in shares_by_ticker and not holding.get("shares_locked"):
                holding["shares"] = float(shares_by_ticker[ticker])
                if reset_manual:
                    holding["manual_shares"] = False
        self._write_portfolio_file(payload)
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

    def add_candidate(
        self,
        portfolio_id: str,
        *,
        ticker: str,
        market: str,
    ) -> Optional[dict[str, Any]]:
        return self.add_candidates_batch(
            portfolio_id,
            entries=[(ticker.strip(), market)],
        )

    def add_candidates_batch(
        self,
        portfolio_id: str,
        *,
        entries: list[tuple[str, str]],
    ) -> Optional[dict[str, Any]]:
        if not entries:
            return self._read_portfolio_file(portfolio_id)

        with self._lock_for(portfolio_id):
            payload = self._read_portfolio_file(portfolio_id)
            if not payload:
                return None

            candidates = payload.setdefault("candidates", [])
            if not isinstance(candidates, list):
                candidates = []
                payload["candidates"] = candidates

            existing = {(str(row.get("ticker")), str(row.get("market"))) for row in candidates if isinstance(row, dict) and row.get("ticker") and row.get("market")}
            changed = False
            for ticker, market in entries:
                normalized_ticker = ticker.strip()
                key = (normalized_ticker, market)
                if key in existing:
                    changed = True
                    continue
                candidates.append(
                    {
                        "ticker": normalized_ticker,
                        "market": market,
                        "added_at": _utc_now_iso(),
                    }
                )
                existing.add(key)
                changed = True

            if not changed:
                return payload

            payload["updated_at"] = _utc_now_iso()
            self._write_portfolio_file(payload)
            self._upsert_index_row(payload)
            self._save_index()
            return payload

    def add_holding(
        self,
        portfolio_id: str,
        *,
        ticker: str,
        market: str,
        shares: float = 0.0,
    ) -> Optional[dict[str, Any]]:
        payload = self.add_candidate(
            portfolio_id,
            ticker=ticker,
            market=market,
        )
        if not payload:
            return None
        holdings = payload.setdefault("holdings", [])
        canonical = ticker.strip()
        if not any(isinstance(row, dict) and str(row.get("ticker")) == canonical and str(row.get("market")) == market for row in holdings):
            holdings.append(
                {
                    "ticker": canonical,
                    "market": market,
                    "shares": float(shares),
                    "manual_shares": False,
                    "shares_locked": False,
                    "open_date": None,
                    "open_date_locked": False,
                    "cost_override": None,
                    "cost_locked": False,
                    "added_at": _utc_now_iso(),
                }
            )
            self._write_portfolio_file(payload)
        return payload

    def _candidate_row_matches(
        self,
        row: Any,
        *,
        ticker: str,
        market: Optional[str],
    ) -> bool:
        if not isinstance(row, dict):
            return False
        if str(row.get("ticker")) != ticker:
            return False
        if market is None:
            return True
        return str(row.get("market")) == market

    def remove_candidate(
        self,
        portfolio_id: str,
        *,
        ticker: str,
        market: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        return self.remove_candidates_batch(
            portfolio_id,
            entries=[(ticker.strip(), market)],
            single_entry_not_found_returns_none=True,
        )

    def remove_candidates_batch(
        self,
        portfolio_id: str,
        *,
        entries: list[tuple[str, Optional[str]]],
        single_entry_not_found_returns_none: bool = False,
    ) -> Optional[dict[str, Any]]:
        if not entries:
            return self._read_portfolio_file(portfolio_id)

        with self._lock_for(portfolio_id):
            payload = self._read_portfolio_file(portfolio_id)
            if not payload:
                return None

            candidates = payload.setdefault("candidates", [])
            if not isinstance(candidates, list):
                candidates = []
                payload["candidates"] = candidates

            targets = [(ticker.strip(), market) for ticker, market in entries if ticker.strip()]
            if not targets:
                return payload

            before = len(candidates)

            def _should_remove(row: Any) -> bool:
                return any(self._candidate_row_matches(row, ticker=target_ticker, market=target_market) for target_ticker, target_market in targets)

            payload["candidates"] = [row for row in candidates if not _should_remove(row)]
            if len(payload["candidates"]) == before:
                if single_entry_not_found_returns_none and len(targets) == 1:
                    return None
                return payload

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
        payload = self.remove_candidate(
            portfolio_id,
            ticker=ticker,
            market=market,
        )
        if not payload:
            return None
        payload["holdings"] = [
            row
            for row in payload.get("holdings") or []
            if not self._candidate_row_matches(
                row,
                ticker=ticker,
                market=market,
            )
        ]
        self._write_portfolio_file(payload)
        return payload

    def add_order(
        self,
        portfolio_id: str,
        *,
        order: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        payload = self._read_portfolio_file(portfolio_id)
        if not payload:
            return None
        orders = payload.setdefault("orders", [])
        if not isinstance(orders, list):
            orders = []
            payload["orders"] = orders
        orders.append(order)
        payload["updated_at"] = _utc_now_iso()
        self._write_portfolio_file(payload)
        self._upsert_index_row(payload)
        self._save_index()
        return payload

    def save_orders(self, portfolio_id: str, orders: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        payload = self._read_portfolio_file(portfolio_id)
        if not payload:
            return None
        payload["orders"] = orders
        payload["updated_at"] = _utc_now_iso()
        self._write_portfolio_file(payload)
        self._upsert_index_row(payload)
        self._save_index()
        return payload

    def cancel_order(self, portfolio_id: str, *, order_id: str) -> Optional[dict[str, Any]]:
        payload = self._read_portfolio_file(portfolio_id)
        if not payload:
            return None
        orders = payload.get("orders") or []
        changed = False
        next_orders: list[dict[str, Any]] = []
        for row in orders:
            if not isinstance(row, dict):
                continue
            if str(row.get("id")) == order_id and str(row.get("order_status")) == "pending":
                next_orders.append({**row, "order_status": "cancelled", "updated_at": _utc_now_iso()})
                changed = True
            else:
                next_orders.append(row)
        if not changed:
            return None
        payload["orders"] = next_orders
        payload["updated_at"] = _utc_now_iso()
        self._write_portfolio_file(payload)
        self._upsert_index_row(payload)
        self._save_index()
        return payload

    def stats(self) -> dict[str, int]:
        return {"total": len(self.list_index_rows())}
