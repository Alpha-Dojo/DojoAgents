from __future__ import annotations

import json
from bisect import bisect_right
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from dojoagents.config.loader import FinancialDashboardConfig
from dojoagents.dashboard.services.domain_utils import normalize_market_code, sanitize_records
from dojoagents.dashboard.services.market_window import (
    MAX_MARKET_WINDOW_DAYS,
    MarketAnalysisWindow,
    resolve_window_bounds_from_trade_dates,
)
from dojoagents.dashboard.jobs.precompute.sector_daily import (
    CONSTITUENTS_FILE,
    MANIFEST_FILE,
    PRECOMPUTE_DIR,
    SECTOR_DAILY_FILE,
    TICKER_DAILY_FILE,
)
from dojoagents.dashboard.services.sector_return_coverage import (
    clip_frame_to_market_as_of,
    filter_usable_sector_daily_rows,
    resolve_market_as_of_by_market,
    restrict_frame_to_market_as_of_exact,
)
from dojoagents.dashboard.services.stock_quote_filter import filter_constituents_frame_by_ticker_cap_min
from dojoagents.logging import LOGGER
from dojoagents.utils.async_runtime import run_sync_bounded


def _clip_daily_frame_for_window(
    df: pd.DataFrame,
    window: MarketAnalysisWindow,
    as_of_by_market: dict[str, str],
    *,
    restrict_latest_one_session: bool = False,
) -> pd.DataFrame:
    """Clip a daily panel to the window's right edge before session compounding."""
    if df.empty:
        return df
    if window.mode == "as_of" and window.as_of:
        requested = str(window.as_of)
        if as_of_by_market:
            clipped = {market: min(str(latest), requested) for market, latest in as_of_by_market.items()}
            df = clip_frame_to_market_as_of(df, clipped)
        if "trade_date" in df.columns and not df.empty:
            df = df.loc[df["trade_date"].astype(str) <= requested].copy()
        return df
    if not as_of_by_market:
        return df
    df = clip_frame_to_market_as_of(df, as_of_by_market)
    if not restrict_latest_one_session:
        return df
    if window.mode != "date_range" and window.days <= 1:
        return restrict_frame_to_market_as_of_exact(df, as_of_by_market)
    if window.mode == "date_range" and window.start_date and window.end_date and str(window.start_date) == str(window.end_date):
        return restrict_frame_to_market_as_of_exact(
            df,
            {market: str(window.end_date) for market in as_of_by_market},
        )
    return df


def dedupe_constituent_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per (market, ticker), matching sector index precompute."""
    if not rows:
        return []
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("market") or ""),
            str(row.get("ticker") or ""),
            str(row.get("role") or ""),
        ),
    )
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for row in sorted_rows:
        key = (str(row.get("market") or ""), str(row.get("ticker") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


SDK_PRECOMPUTED_PATHS = (
    "/api/qdata/v1/sector/precomputed/constituents",
    "/api/qdata/v1/sector/precomputed/sector_daily",
    "/api/qdata/v1/sector/precomputed/ticker_daily",
)

# ``ticker_daily`` holds a row per (market, ticker, session) — millions of rows
# after a full-window rebuild — while every Dashboard consumer only asks for a
# bounded window. Keep only the most recent sessions in memory and read older
# ranges from parquet on demand. The resident tail is sized from the published
# window bound (``days <= MAX_MARKET_WINDOW_DAYS``) plus a small margin, so every
# routine request is answered by slicing memory and never touches disk.
TICKER_TAIL_SESSIONS = MAX_MARKET_WINDOW_DAYS + 10
_TICKER_RANGE_CACHE_MAX = 4
# Row budget for *non-tail* (parquet-backed) windows: bounds how much extra
# history a burst of ``as_of``/``date_range`` browsing can pin.
_TICKER_RANGE_CACHE_ROWS = 600_000
_TICKER_BOUNDS_BATCH = 250_000

# Cap on memoized per-window results. ``days`` mode is naturally bounded by
# ``MAX_MARKET_WINDOW_DAYS``; ``as_of`` mode is not, so a cap keeps a long
# browsing session from accumulating computed frames.
_WINDOW_CACHE_MAX = 64


def _filter_trade_date_range(
    frame: pd.DataFrame,
    start: Optional[str],
    end: Optional[str],
) -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame
    if not start and not end:
        return frame
    dates = frame["trade_date"].astype(str)
    mask = pd.Series(True, index=frame.index)
    if start:
        mask &= dates >= str(start)
    if end:
        mask &= dates <= str(end)
    return frame.loc[mask]


def _read_ticker_range(path: Path, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    """Rows of a ticker_daily parquet inside ``[start, end]``, read in batches.

    The publisher writes row groups that each span the whole history, so
    row-group statistics cannot prune and ``read_parquet(filters=...)``
    materializes far more than it returns. Scanning batches keeps the peak near
    one batch plus the retained rows (~40% lower than the filter path on the
    current 3.7M-row file, measured) and works regardless of file layout.
    """
    if not start and not end:
        return pd.read_parquet(path)
    try:
        import pyarrow.parquet as pq
    except Exception:  # pragma: no cover - pyarrow is a pandas parquet engine
        return _filter_trade_date_range(pd.read_parquet(path), start, end)

    parts: list[pd.DataFrame] = []
    for batch in pq.ParquetFile(path).iter_batches(batch_size=_TICKER_BOUNDS_BATCH):
        part = batch.to_pandas()
        if part.empty:
            continue
        hit = _filter_trade_date_range(part, start, end)
        if not hit.empty:
            parts.append(hit)
    if not parts:
        return pd.DataFrame()
    if len(parts) == 1:
        return parts[0]
    return pd.concat(parts, ignore_index=True)


class SectorPrecomputedStore:
    def __init__(self, data_root: Path | None = None, *, snapshot_client: Any | None = None) -> None:
        self.data_root = Path(data_root or FinancialDashboardConfig.dashboard_data_root).expanduser().resolve()
        self.dataset_dir = self.data_root / PRECOMPUTE_DIR
        self.snapshot_client = snapshot_client
        self._constituents_df: Optional[pd.DataFrame] = None
        self._sector_daily_df: Optional[pd.DataFrame] = None
        self._manifest: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._load_generation = 0
        self._constituents_exact_index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        self._sector_daily_index: Optional[pd.DataFrame] = None
        self._sector_window_cache: OrderedDict[tuple[str, ...], pd.DataFrame] = OrderedDict()
        self._ticker_window_cache: OrderedDict[tuple[str, ...], pd.DataFrame] = OrderedDict()
        # ticker_daily is kept out of memory as a full frame: source parquet
        # paths + a bounded recent tail, with on-demand range reads.
        self._ticker_daily_paths: list[Path] = []
        self._ticker_daily_df: Optional[pd.DataFrame] = None
        self._ticker_sessions: Optional[list[str]] = None
        # Per-market *upper bound* (naive max trade_date) learned while streaming
        # metadata. The published as-of is the coverage-gated value computed from
        # the bounded tail (:meth:`_ticker_as_of_by_market`); this naive bound only
        # backs up markets that no longer appear in the tail at all.
        self._ticker_as_of: Optional[dict[str, str]] = None
        self._ticker_as_of_gated: Optional[dict[str, str]] = None
        self._ticker_total_rows: int = 0
        self._ticker_tail_start: Optional[str] = None
        self._ticker_range_cache: OrderedDict[tuple[Optional[str], Optional[str]], pd.DataFrame] = OrderedDict()

    def available(self) -> bool:
        return self._sector_daily_df is not None or (
            self.dataset_dir.exists() and (self.dataset_dir / MANIFEST_FILE).exists()
        )

    def data_revision(self) -> Optional[str]:
        """Identity of the currently loaded precomputed data (for cache guards).

        Returns None when nothing (or revision-unidentifiable data) is loaded;
        consumers should skip invalidation checks in that case.
        """
        manifest = self._manifest or {}
        revision = manifest.get("resolved_revision") or manifest.get("build_id")
        return str(revision) if revision else None

    async def load(self) -> None:
        await self.reload_async()

    async def reload_async(self, dataset_dir: Path | None = None) -> None:
        if dataset_dir is None and self.snapshot_client is not None:
            try:
                snapshots = await self.snapshot_client.ensure_offline_snapshots(
                    paths=list(SDK_PRECOMPUTED_PATHS)
                )
                if snapshots:
                    await run_sync_bounded(self._load_sdk_snapshot, snapshots[0])
                    return
            except Exception as exc:
                LOGGER.warning(
                    "Failed to load SDK sector-precomputed snapshot; falling back to Dashboard publish: %s",
                    exc,
                )
        await run_sync_bounded(self.reload, dataset_dir)

    def _load_sdk_snapshot(self, snapshot: Any) -> None:
        files = {str(item.relative_path): Path(item.local_path) for item in snapshot.files}
        missing = [name for name in (CONSTITUENTS_FILE, SECTOR_DAILY_FILE, TICKER_DAILY_FILE) if name not in files]
        if missing:
            raise FileNotFoundError(
                "SDK sector-precomputed snapshot is missing: " + ", ".join(missing)
            )
        constituents_df = self._normalize_constituents_frame(pd.read_parquet(files[CONSTITUENTS_FILE]))
        sector_daily_df = self._normalize_sector_daily_frame(pd.read_parquet(files[SECTOR_DAILY_FILE]))
        # The SDK repository may publish only the markets changed in the latest
        # revision. Preserve the Dashboard's full local baseline and overlay
        # snapshot rows by their natural keys instead of dropping other markets.
        local_manifest = self.dataset_dir / MANIFEST_FILE
        local_ticker_path = self.dataset_dir / TICKER_DAILY_FILE
        if local_manifest.exists() and local_ticker_path.exists():
            try:
                local_constituents = self._normalize_constituents_frame(
                    pd.read_parquet(self.dataset_dir / CONSTITUENTS_FILE)
                )
                local_sector_daily = self._normalize_sector_daily_frame(
                    pd.read_parquet(self.dataset_dir / SECTOR_DAILY_FILE)
                )
                constituents_df = self._overlay_frames(
                    local_constituents,
                    constituents_df,
                    keys=["market", "ticker", "level1_id", "level2_id", "level3_id", "role"],
                )
                sector_daily_df = self._overlay_frames(
                    local_sector_daily,
                    sector_daily_df,
                    keys=["trade_date", "scope", "market", "level1_id", "level2_id", "level3_id"],
                )
            except Exception as exc:
                LOGGER.warning("Failed to merge local sector baseline with SDK snapshot: %s", exc)
        if self._constituents_df is not None:
            constituents_df = self._overlay_frames(
                self._constituents_df,
                constituents_df,
                keys=["market", "ticker", "level1_id", "level2_id", "level3_id", "role"],
            )
        if self._sector_daily_df is not None:
            sector_daily_df = self._overlay_frames(
                self._sector_daily_df,
                sector_daily_df,
                keys=["trade_date", "scope", "market", "level1_id", "level2_id", "level3_id"],
            )
        ticker_paths = [files[TICKER_DAILY_FILE]]
        if local_manifest.exists() and local_ticker_path.exists():
            # Local publish first, SDK snapshot last: overlay keeps "last", so
            # snapshot rows win on duplicate (market, ticker, trade_date).
            ticker_paths = [local_ticker_path, files[TICKER_DAILY_FILE]]
        self._register_ticker_sources(ticker_paths)
        self._constituents_df = constituents_df
        self._sector_daily_df = sector_daily_df
        self._manifest = {
            "source": "dojosdk_snapshot",
            "backend": str(snapshot.backend),
            "repo_id": str(snapshot.repo_id),
            "resolved_revision": str(snapshot.resolved_revision),
            "snapshot_token": str(snapshot.snapshot_token),
        }
        self._last_error = None
        self._rebuild_indexes_locked()

    @staticmethod
    def _overlay_frames(
        baseline: pd.DataFrame,
        update: pd.DataFrame,
        *,
        keys: list[str],
    ) -> pd.DataFrame:
        if baseline.empty:
            return update
        if update.empty:
            return baseline
        usable_keys = [key for key in keys if key in baseline.columns and key in update.columns]
        if not usable_keys:
            return update
        return pd.concat([baseline, update], ignore_index=True).drop_duplicates(
            subset=usable_keys,
            keep="last",
        )

    def reload(self, dataset_dir: Path | None = None) -> None:
        target_dir = Path(dataset_dir).expanduser().resolve() if dataset_dir else self.dataset_dir

        manifest_path = target_dir / MANIFEST_FILE
        if manifest_path.exists():
            try:
                constituents_df = self._normalize_constituents_frame(pd.read_parquet(target_dir / CONSTITUENTS_FILE))
                sector_daily_df = self._normalize_sector_daily_frame(pd.read_parquet(target_dir / SECTOR_DAILY_FILE))
                ticker_path = target_dir / TICKER_DAILY_FILE
                if not ticker_path.exists():
                    raise FileNotFoundError(f"missing {TICKER_DAILY_FILE} in {target_dir}")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                self._last_error = f"local_reload_failed: {exc}"
                LOGGER.warning("Failed to reload local sector precomputed snapshot: %s", exc)
                self.clear_cache()
            else:
                self.dataset_dir = target_dir
                self._constituents_df = constituents_df
                self._sector_daily_df = sector_daily_df
                self._register_ticker_sources([ticker_path])
                self._manifest = manifest
                self._last_error = None
                self._rebuild_indexes_locked()
                return

        self._last_error = "dataset_missing"
        LOGGER.error("Sector precomputed local publish dataset is missing: %s", target_dir)
        self.clear_cache()

    def _register_ticker_sources(self, paths: list[Path]) -> None:
        """Point the store at ticker_daily parquet files instead of loading them.

        ``ticker_daily`` is only ever queried by bounded window, so the frames are
        read on demand (see :meth:`_ticker_panel`) and never held in full.
        """
        ordered: list[Path] = []
        for path in paths:
            resolved = Path(path).expanduser()
            if resolved not in ordered:
                ordered.append(resolved)
        self._ticker_daily_paths = ordered
        self._ticker_daily_df = None
        self._ticker_sessions = None
        self._ticker_as_of = None
        self._ticker_as_of_gated = None
        self._ticker_total_rows = 0
        self._ticker_tail_start = None
        self._ticker_range_cache = OrderedDict()

    def _ensure_ticker_metadata(self) -> None:
        """Stream ticker_daily once to learn sessions, per-market as-of and row count.

        Only the ``market``/``trade_date`` columns are decoded, one batch at a
        time, so this never materializes the multi-million-row frame.
        """
        if self._ticker_sessions is not None:
            return
        if not self._ticker_daily_paths:
            # No parquet sources registered: treat an in-memory frame (seeded by
            # tests or by a caller) as the whole dataset.
            seeded = self._ticker_daily_df
            if seeded is None or seeded.empty:
                self._ticker_sessions = []
                self._ticker_as_of = {}
                self._ticker_total_rows = 0
                self._ticker_tail_start = None
                return
            dates = seeded["trade_date"].astype(str)
            self._ticker_sessions = sorted(dates.unique().tolist())
            self._ticker_as_of = {
                str(market): str(day)
                for market, day in seeded.assign(_trade_date=dates).groupby("market", sort=False)["_trade_date"].max().items()
            }
            self._ticker_total_rows = len(seeded)
            self._ticker_tail_start = self._ticker_sessions[0]
            return
        sessions: set[str] = set()
        as_of: dict[str, str] = {}
        total = 0
        try:
            import pyarrow.parquet as pq
        except Exception:  # pragma: no cover - pyarrow is a pandas parquet engine
            pq = None
        for path in self._ticker_daily_paths:
            try:
                if pq is None:
                    frame = self._normalize_ticker_daily_frame(pd.read_parquet(path))
                    total += len(frame)
                    sessions.update(frame["trade_date"].astype(str).tolist())
                    continue
                parquet = pq.ParquetFile(path)
                names = set(parquet.schema_arrow.names)
                columns = [name for name in ("market", "trade_date") if name in names]
                if "trade_date" not in columns:
                    continue
                for batch in parquet.iter_batches(batch_size=_TICKER_BOUNDS_BATCH, columns=columns):
                    frame = batch.to_pandas()
                    if frame.empty:
                        continue
                    total += len(frame)
                    dates = frame["trade_date"].astype(str)
                    sessions.update(dates.tolist())
                    if "market" in frame.columns:
                        grouped = (
                            frame.assign(_trade_date=dates)
                            .groupby("market", sort=False)["_trade_date"]
                            .max()
                        )
                        for market, day in grouped.items():
                            key = normalize_market_code(str(market)) or str(market)
                            if day and (key not in as_of or day > as_of[key]):
                                as_of[key] = str(day)
            except Exception as exc:
                LOGGER.warning("Failed to inspect ticker_daily source %s: %s", path, exc)
        self._ticker_sessions = sorted(sessions)
        self._ticker_as_of = as_of
        self._ticker_total_rows = total
        if self._ticker_sessions:
            floor = max(len(self._ticker_sessions) - TICKER_TAIL_SESSIONS, 0)
            self._ticker_tail_start = self._ticker_sessions[floor]

    def _ticker_as_of_by_market(self) -> dict[str, str]:
        """Per-market as-of with the thin-trailing-bar coverage gate applied.

        Computed from the bounded tail rather than the full multi-million-row
        frame: the gate only ever *removes* the last few sparse sessions, so every
        candidate it can consider lies inside the tail. Markets absent from the
        tail fall back to the streamed naive max so a long-dormant market is still
        clipped to its last print.
        """
        self._ensure_ticker_metadata()
        if self._ticker_as_of_gated is not None:
            return dict(self._ticker_as_of_gated)
        gated = resolve_market_as_of_by_market(self._load_ticker_daily())
        if gated:
            for market, day in (self._ticker_as_of or {}).items():
                if day:
                    gated.setdefault(str(market), str(day))
        else:
            gated = dict(self._ticker_as_of or {})
        self._ticker_as_of_gated = gated
        return dict(gated)

    def _ticker_sessions_list(self) -> list[str]:
        self._ensure_ticker_metadata()
        return list(self._ticker_sessions or [])

    def _ticker_panel(
        self,
        start: Optional[str],
        end: Optional[str] = None,
        *,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Long ticker_daily frame for ``[start, end]``.

        Resolution order keeps routine traffic off disk and out of duplicate
        memory:

        1. an in-memory frame seeded by a caller (no parquet sources registered);
        2. slice the resident tail when the whole range lies inside it — this is
           the ``days <= MAX_MARKET_WINDOW_DAYS`` path, i.e. every routine request;
        3. otherwise read the range from parquet, caching it only while it stays
           inside the row budget.
        """
        self._ensure_ticker_metadata()
        key = (str(start) if start else None, str(end) if end else None)

        if not self._ticker_daily_paths:
            seeded = self._ticker_daily_df
            return _filter_trade_date_range(seeded, *key) if seeded is not None else pd.DataFrame()

        tail = self._ticker_daily_df
        tail_start = self._ticker_tail_start
        if tail is not None and tail_start and (key[0] is None or key[0] >= tail_start):
            # Fully inside the resident tail: slice it. Nothing extra is retained.
            return _filter_trade_date_range(tail, *key)

        if use_cache:
            cached = self._ticker_range_cache.get(key)
            if cached is not None:
                self._ticker_range_cache.move_to_end(key)
                return cached

        frames: list[pd.DataFrame] = []
        for path in self._ticker_daily_paths:
            try:
                frame = _read_ticker_range(path, *key)
            except Exception as exc:
                LOGGER.warning("Failed to read ticker_daily window from %s: %s", path, exc)
                continue
            if frame.empty:
                continue
            frames.append(self._normalize_ticker_daily_frame(frame))

        if not frames:
            panel = pd.DataFrame()
        elif len(frames) == 1:
            panel = frames[0]
        else:
            panel = pd.concat(frames, ignore_index=True).drop_duplicates(
                subset=["trade_date", "market", "ticker"],
                keep="last",
            )
        panel = _filter_trade_date_range(panel, *key)

        if use_cache and len(panel) <= _TICKER_RANGE_CACHE_ROWS:
            self._ticker_range_cache[key] = panel
            while len(self._ticker_range_cache) > _TICKER_RANGE_CACHE_MAX:
                self._ticker_range_cache.popitem(last=False)
        return panel

    def _panel_start_for_window(self, window: MarketAnalysisWindow) -> Optional[str]:
        """Earliest session needed to answer ``window`` (clamped to the tail)."""
        sessions = self._ticker_sessions_list()
        if not sessions:
            return None
        if window.mode == "date_range":
            return str(window.start_date) if window.start_date else None
        days = max(int(window.days or 1), 1)
        if window.mode == "as_of" and window.as_of:
            right = min(str(window.as_of), sessions[-1])
            index = bisect_right(sessions, right) - 1
            if index < 0:
                # Requested as_of precedes the stored history; nothing to read.
                return right
        else:
            index = len(sessions) - 1
        return sessions[max(index - days, 0)]

    def _panel_end_for_window(self, window: MarketAnalysisWindow) -> Optional[str]:
        """Latest session ``window`` can need (``None`` = no upper bound).

        Bounding the right edge too keeps a historical ``date_range``/``as_of``
        request from reading every session up to today. It is safe because the
        window clip and ``_compute_date_range_frame`` both drop rows past the
        window's own end anyway.
        """
        if window.mode == "date_range":
            return str(window.end_date) if window.end_date else None
        if window.mode == "as_of" and window.as_of:
            return str(window.as_of)
        return None

    def _load_constituents(self) -> pd.DataFrame:
        return self._constituents_df if self._constituents_df is not None else pd.DataFrame()

    def _load_sector_daily(self) -> pd.DataFrame:
        return self._sector_daily_df if self._sector_daily_df is not None else pd.DataFrame()

    def _load_ticker_daily(self) -> pd.DataFrame:
        """Bounded recent tail of ticker_daily (see :data:`TICKER_TAIL_SESSIONS`).

        Held as ``_ticker_daily_df`` itself, so it is read with ``use_cache=False``
        to avoid registering the same frame twice in the range cache. Metadata must
        be resolved *first*: ``_ticker_tail_start`` is only known after
        :meth:`_ensure_ticker_metadata` streams the sources, and reading it too
        early would pass ``start=None`` and pull the whole multi-million-row file.
        """
        if self._ticker_daily_df is None:
            self._ensure_ticker_metadata()
            self._ticker_daily_df = self._ticker_panel(self._ticker_tail_start, None, use_cache=False)
        return self._ticker_daily_df

    def manifest(self) -> dict[str, Any] | None:
        return self._manifest

    @property
    def load_generation(self) -> int:
        return self._load_generation

    def stats(self) -> dict[str, Any]:
        self._ensure_ticker_metadata()
        tail_rows = 0
        if self._ticker_daily_paths:
            tail_rows = len(self._load_ticker_daily())
        return {
            "available": self.available(),
            "constituents_rows": len(self._load_constituents()),
            "sector_daily_rows": len(self._load_sector_daily()),
            "ticker_daily_rows": int(self._ticker_total_rows),
            "ticker_daily_tail_rows": int(tail_rows),
            "ticker_daily_tail_start": self._ticker_tail_start,
            "last_error": self._last_error,
            "manifest": self._manifest,
        }

    def get_sector_constituents(self, level1_id: str, level2_id: str, level3_id: str, market: Optional[str] = None) -> list[dict]:
        df = self._load_constituents()
        if df.empty:
            return []

        exact = self.get_sector_constituents_exact(level1_id, level2_id, level3_id, market=market)
        if market and level2_id and level3_id and exact:
            return exact

        mask = df["level1_id"] == level1_id
        if level2_id:
            mask &= df["level2_id"] == level2_id
        if level3_id:
            mask &= df["level3_id"] == level3_id
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)

        rows = sanitize_records(df[mask])
        if not level3_id:
            rows = dedupe_constituent_rows(rows)
        return rows

    def get_sector_constituents_exact(
        self,
        level1_id: str,
        level2_id: str,
        level3_id: str,
        market: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        normalized_market = normalize_market_code(market) or market
        if not normalized_market or not level2_id or not level3_id:
            return []
        key = (normalized_market, str(level1_id), str(level2_id), str(level3_id))
        rows = self._constituents_exact_index.get(key)
        return list(rows) if rows is not None else []

    def get_sector_daily(self, scope: str, level1_id: str, level2_id: str, level3_id: str, market: Optional[str] = None) -> list[dict]:
        # Fast path: exact multi-index lookup (avoids a full boolean scan per call).
        if market and self._sector_daily_index is not None:
            level2 = level2_id if scope in ("L2", "L3") else ""
            level3 = level3_id if scope == "L3" else ""
            key = (
                str(scope),
                str(level1_id),
                str(level2),
                str(level3),
                str(normalize_market_code(market) or market),
            )
            try:
                rows = self._sector_daily_index.loc[[key]]
            except KeyError:
                return []
            return sanitize_records(rows.reset_index())

        df = self._load_sector_daily()
        if df.empty:
            return []

        mask = (df["scope"] == scope) & (df["level1_id"] == level1_id)
        if scope in ("L2", "L3"):
            mask &= df["level2_id"] == level2_id
        if scope == "L3":
            mask &= df["level3_id"] == level3_id
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)
        return sanitize_records(df[mask])

    def get_sector_movers(self, date: str) -> list[dict]:
        df = filter_usable_sector_daily_rows(self._load_sector_daily())
        if df.empty:
            return []
        target_date = date or str(df["trade_date"].max())
        return sanitize_records(df[df["trade_date"] == target_date])

    def get_sector_movers_window_frame(self, days: int) -> pd.DataFrame:
        return self.get_sector_movers_window_frame_for_window(
            MarketAnalysisWindow(mode="days", days=days),
        )

    def get_sector_movers_window_frame_for_window(self, window: MarketAnalysisWindow) -> pd.DataFrame:
        # Cached first: a repeat request must not re-copy the 188k-row sector
        # panel through the usability filter.
        cache_key = window.cache_key()
        cached = self._sector_window_cache.get(cache_key)
        if cached is not None:
            return cached
        df = filter_usable_sector_daily_rows(self._load_sector_daily())
        if df.empty:
            return pd.DataFrame()
        as_of_by_market = self._ticker_as_of_by_market()
        df = _clip_daily_frame_for_window(df, window, as_of_by_market)
        if df.empty:
            return pd.DataFrame()
        if window.mode == "date_range":
            computed = self._compute_date_range_frame(
                df,
                group_cols=["scope", "level1_id", "level2_id", "level3_id", "market"],
                value_col="index_level",
                start_date=str(window.start_date or ""),
                end_date=str(window.end_date or ""),
            )
        else:
            computed = self._compute_window_frame(
                df,
                group_cols=["scope", "level1_id", "level2_id", "level3_id", "market"],
                value_col="index_level",
                days=window.days,
            )
        existing = self._sector_window_cache.get(cache_key)
        if existing is not None:
            return existing
        self._store_window_cache_entry(self._sector_window_cache, cache_key, computed)
        return computed

    def resolve_window_bounds(self, window: MarketAnalysisWindow) -> MarketAnalysisWindow:
        df = filter_usable_sector_daily_rows(self._load_sector_daily())
        as_of_by_market = self._ticker_as_of_by_market()
        if as_of_by_market and not df.empty:
            df = _clip_daily_frame_for_window(df, window, as_of_by_market)
        if df.empty or "trade_date" not in df.columns:
            return resolve_window_bounds_from_trade_dates(window, [])
        trade_dates = [str(item) for item in df["trade_date"].tolist()]
        return resolve_window_bounds_from_trade_dates(window, trade_dates)

    def get_sector_movers_by_window(self, days: int) -> list[dict]:
        return sanitize_records(self.get_sector_movers_window_frame(days))

    def get_sector_movers_for_window(self, window: MarketAnalysisWindow) -> list[dict]:
        return sanitize_records(self.get_sector_movers_window_frame_for_window(window))

    def get_ticker_daily(self, date: str, tickers: list[str], market: str | None = None) -> list[dict]:
        df = self._ticker_panel(date, date)
        if df.empty:
            return []
        mask = (df["trade_date"] == date) & (df["ticker"].isin(tickers))
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)
        return sanitize_records(df[mask])

    def get_ticker_daily_window_frame(self, days: int) -> pd.DataFrame:
        return self.get_ticker_daily_window_frame_for_window(
            MarketAnalysisWindow(mode="days", days=days),
        )

    def get_ticker_daily_window_frame_for_window(self, window: MarketAnalysisWindow) -> pd.DataFrame:
        # Serve repeat requests straight from the computed-window cache: the key
        # pins mode/days/as_of/date_range and both the cache and this store's
        # window bounds are reset together on reload, so no read is needed.
        cache_key = window.cache_key()
        cached = self._ticker_window_cache.get(cache_key)
        if cached is not None:
            return cached
        # Read only the sessions the window can reach: routine requests
        # (days <= MAX_MARKET_WINDOW_DAYS, near-latest as_of) are answered by
        # slicing the resident tail, older ranges are read from parquet.
        df = self._ticker_panel(
            self._panel_start_for_window(window),
            self._panel_end_for_window(window),
        )
        if df.empty:
            return pd.DataFrame()
        as_of_by_market = self._ticker_as_of_by_market() or resolve_market_as_of_by_market(df)
        if as_of_by_market:
            df = _clip_daily_frame_for_window(
                df,
                window,
                as_of_by_market,
                restrict_latest_one_session=True,
            )
        if df.empty:
            return pd.DataFrame()
        if window.mode == "date_range":
            computed = self._compute_date_range_frame(
                df,
                group_cols=["market", "ticker"],
                value_col="close",
                start_date=str(window.start_date or ""),
                end_date=str(window.end_date or ""),
            )
        else:
            computed = self._compute_window_frame(
                df,
                group_cols=["market", "ticker"],
                value_col="close",
                days=window.days,
            )
        existing = self._ticker_window_cache.get(cache_key)
        if existing is not None:
            return existing
        self._store_window_cache_entry(self._ticker_window_cache, cache_key, computed)
        return computed

    def get_ticker_daily_by_window(self, days: int, tickers: list[str], market: str | None = None) -> list[dict]:
        return self.get_ticker_daily_for_window(
            MarketAnalysisWindow(mode="days", days=days),
            tickers,
            market=market,
        )

    def get_ticker_daily_for_window(
        self,
        window: MarketAnalysisWindow,
        tickers: list[str],
        market: str | None = None,
    ) -> list[dict]:
        df = self.get_ticker_daily_window_frame_for_window(window)
        if df.empty or not tickers:
            return []

        mask = df["ticker"].isin(tickers)
        if market:
            mask &= df["market"] == (normalize_market_code(market) or market)
        return sanitize_records(df[mask])

    def clear_cache(self) -> None:
        self._constituents_df = None
        self._sector_daily_df = None
        self._manifest = None
        self._constituents_exact_index = {}
        self._sector_daily_index = None
        self._sector_window_cache = OrderedDict()
        self._ticker_window_cache = OrderedDict()
        self._register_ticker_sources([])
        self._load_generation += 1

    def _rebuild_indexes_locked(self) -> None:
        self._constituents_exact_index = {}
        self._sector_daily_index = None
        self._sector_window_cache = OrderedDict()
        self._ticker_window_cache = OrderedDict()
        self._ticker_range_cache = OrderedDict()
        self._ticker_as_of_gated = None
        self._load_generation += 1

        sector_daily = self._sector_daily_df
        if sector_daily is not None and not sector_daily.empty:
            index_cols = ["scope", "level1_id", "level2_id", "level3_id", "market"]
            if all(col in sector_daily.columns for col in index_cols):
                self._sector_daily_index = sector_daily.set_index(index_cols).sort_index()

        df = self._constituents_df
        if df is None or df.empty:
            return
        for row in sanitize_records(df):
            key = (
                str(row.get("market") or ""),
                str(row.get("level1_id") or ""),
                str(row.get("level2_id") or ""),
                str(row.get("level3_id") or ""),
            )
            self._constituents_exact_index.setdefault(key, []).append(row)

    @staticmethod
    def _store_window_cache_entry(
        cache: OrderedDict[tuple[str, ...], pd.DataFrame],
        key: tuple[str, ...],
        frame: pd.DataFrame,
    ) -> None:
        """Insert a computed window frame, evicting the oldest entries past the cap.

        Bounds per-page memoization so an open Dashboard session cannot pin an
        unbounded number of computed frames (see :data:`_WINDOW_CACHE_MAX`).
        """
        cache[key] = frame
        cache.move_to_end(key)
        while len(cache) > _WINDOW_CACHE_MAX:
            cache.popitem(last=False)

    @staticmethod
    def _normalize_constituents_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        normalized = df.copy()
        for col in ("market", "ticker", "level1_id", "level2_id", "level3_id"):
            if col in normalized.columns:
                normalized[col] = normalized[col].astype(str)
        filtered = filter_constituents_frame_by_ticker_cap_min(normalized)
        dropped = len(normalized) - len(filtered)
        if dropped:
            LOGGER.warning(
                "Dropped %s sector constituents at/below ticker market-cap floor on reload " "(stale snapshot or misconfigured publish).",
                dropped,
            )
        return filtered

    @staticmethod
    def _normalize_sector_daily_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        normalized = df
        for col in ("scope", "market", "level1_id", "level2_id", "level3_id", "trade_date"):
            if col in normalized.columns:
                normalized[col] = normalized[col].astype(str)
        return normalized

    @staticmethod
    def _normalize_ticker_daily_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        normalized = df
        for col in ("market", "ticker", "trade_date"):
            if col in normalized.columns:
                normalized[col] = normalized[col].astype(str)
        return normalized

    @staticmethod
    def _compute_window_frame(
        df: pd.DataFrame,
        *,
        group_cols: list[str],
        value_col: str,
        days: int,
    ) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        sort_cols = [*group_cols, "trade_date"]
        df_sorted = df.sort_values(by=sort_cols).reset_index(drop=True)
        if days <= 1:
            return df_sorted.groupby(group_cols, sort=False, as_index=False).tail(1)

        group_sizes = df_sorted.groupby(group_cols, sort=False)["trade_date"].transform("size")
        positions = df_sorted.groupby(group_cols, sort=False).cumcount()
        latest_mask = positions == (group_sizes - 1)
        latest_rows = df_sorted[latest_mask].copy()

        if "daily_return_pct" in df_sorted.columns:
            in_window = positions >= (group_sizes - days).clip(lower=0)
            window_rows = df_sorted.loc[in_window].copy()
            factors = 1.0 + pd.to_numeric(window_rows["daily_return_pct"], errors="coerce") / 100.0
            window_rows = window_rows.assign(_session_factor=factors)
            compounded = window_rows.groupby(group_cols, sort=False)["_session_factor"].prod().rename("_compound_factor")
            merged = latest_rows.merge(compounded.reset_index(), on=group_cols, how="left")
            factor = pd.to_numeric(merged["_compound_factor"], errors="coerce")
            merged["daily_return_pct"] = (factor - 1.0) * 100.0
            invalid = factor.isna() | (factor <= 0)
            merged.loc[invalid, "daily_return_pct"] = 0.0
            merged["daily_return_pct"] = merged["daily_return_pct"].fillna(0.0)
            if "change_percent" in merged.columns:
                merged = merged.drop(columns=["change_percent"])
            return merged.drop(columns=["_compound_factor"], errors="ignore")

        prior_positions = group_sizes - days - 1
        start_positions = prior_positions.clip(lower=0)
        start_mask = positions == start_positions
        start_rows = df_sorted[start_mask][group_cols + [value_col]].rename(columns={value_col: "_window_start_value"})
        merged = latest_rows.merge(start_rows, on=group_cols, how="left")

        latest_values = pd.to_numeric(merged[value_col], errors="coerce")
        start_values = pd.to_numeric(merged["_window_start_value"], errors="coerce")
        merged["daily_return_pct"] = ((latest_values / start_values) - 1.0) * 100.0
        invalid = start_values.isna() | latest_values.isna() | (start_values <= 0)
        merged.loc[invalid, "daily_return_pct"] = 0.0
        merged["daily_return_pct"] = merged["daily_return_pct"].fillna(0.0)
        if "change_percent" in merged.columns:
            merged = merged.drop(columns=["change_percent"])
        return merged.drop(columns=["_window_start_value"], errors="ignore")

    @staticmethod
    def _compute_date_range_frame(
        df: pd.DataFrame,
        *,
        group_cols: list[str],
        value_col: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        sort_cols = [*group_cols, "trade_date"]
        df_sorted = df.sort_values(by=sort_cols).reset_index(drop=True)
        mask = (df_sorted["trade_date"] >= start_date) & (df_sorted["trade_date"] <= end_date)
        filtered = df_sorted[mask]
        if filtered.empty:
            return pd.DataFrame()

        if start_date == end_date:
            single_day = filtered.groupby(group_cols, sort=False, as_index=False).tail(1)
            if "daily_return_pct" not in single_day.columns:
                single_day["daily_return_pct"] = 0.0
            return single_day

        last_rows = filtered.groupby(group_cols, sort=False, as_index=False).tail(1)

        # Same contract as as_of/days: compound every session daily return in the inclusive
        # trade-date window. Using last/first index_level omits the first session's return.
        if "daily_return_pct" in filtered.columns:
            factors = 1.0 + pd.to_numeric(filtered["daily_return_pct"], errors="coerce") / 100.0
            window_rows = filtered.assign(_session_factor=factors)
            compounded = window_rows.groupby(group_cols, sort=False)["_session_factor"].prod().rename("_compound_factor")
            merged = last_rows.merge(compounded.reset_index(), on=group_cols, how="left")
            factor = pd.to_numeric(merged["_compound_factor"], errors="coerce")
            merged["daily_return_pct"] = (factor - 1.0) * 100.0
            invalid = factor.isna() | (factor <= 0)
            merged.loc[invalid, "daily_return_pct"] = 0.0
            merged["daily_return_pct"] = merged["daily_return_pct"].fillna(0.0)
            if "change_percent" in merged.columns:
                merged = merged.drop(columns=["change_percent"])
            return merged.drop(columns=["_compound_factor"], errors="ignore")

        first_rows = filtered.groupby(group_cols, sort=False, as_index=False).head(1)
        start_values = first_rows[group_cols + [value_col]].rename(columns={value_col: "_window_start_value"})
        merged = last_rows.merge(start_values, on=group_cols, how="left")

        latest_values = pd.to_numeric(merged[value_col], errors="coerce")
        start_values_numeric = pd.to_numeric(merged["_window_start_value"], errors="coerce")
        merged["daily_return_pct"] = ((latest_values / start_values_numeric) - 1.0) * 100.0
        invalid = start_values_numeric.isna() | latest_values.isna() | (start_values_numeric <= 0)
        merged.loc[invalid, "daily_return_pct"] = 0.0
        merged["daily_return_pct"] = merged["daily_return_pct"].fillna(0.0)
        if "change_percent" in merged.columns:
            merged = merged.drop(columns=["change_percent"])
        return merged.drop(columns=["_window_start_value"], errors="ignore")
