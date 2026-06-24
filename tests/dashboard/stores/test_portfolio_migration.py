from __future__ import annotations

import json

from dojoagents.dashboard.services.portfolio_store import PortfolioStore


def _write_v1(root) -> tuple[object, bytes]:
    portfolio_root = root / "portfolio"
    portfolio_root.mkdir(parents=True)
    path = portfolio_root / "p1.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "id": "p1",
                "name": "Legacy",
                "holdings": [
                    {
                        "ticker": "AAPL",
                        "market": "us",
                        "shares": 10,
                        "manual_shares": True,
                        "open_date": "2025-01-02",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path, path.read_bytes()


def test_v1_portfolio_load_does_not_mutate_detail_file(tmp_path) -> None:
    path, original = _write_v1(tmp_path)

    store = PortfolioStore(tmp_path)

    assert store.get_raw("p1")["version"] == 1
    assert path.read_bytes() == original


def test_portfolio_migration_dry_run_reports_without_writing(tmp_path) -> None:
    path, original = _write_v1(tmp_path)
    store = PortfolioStore(tmp_path)

    report = store.migrate_to_v2(dry_run=True)

    assert report["would_migrate"] == ["p1"]
    assert report["migrated"] == []
    assert report["errors"] == []
    assert path.read_bytes() == original
    assert not (path.parent / "p1.json.v1.bak").exists()


def test_portfolio_migration_backs_up_and_applies_v2_mapping(tmp_path) -> None:
    path, original = _write_v1(tmp_path)
    store = PortfolioStore(tmp_path)

    report = store.migrate_to_v2(dry_run=False)

    payload = json.loads(path.read_text(encoding="utf-8"))
    holding = payload["holdings"][0]
    assert report["migrated"] == ["p1"]
    assert payload["version"] == 2
    assert payload["pinned"] is False
    assert holding["shares_locked"] is True
    assert holding["open_date_locked"] is False
    assert holding["cost_override"] is None
    assert holding["cost_locked"] is False
    assert (path.parent / "p1.json.v1.bak").read_bytes() == original
    assert json.loads((path.parent / "index.json").read_text(encoding="utf-8"))["version"] == 2


def test_corrupt_portfolio_is_reported_and_preserved(tmp_path) -> None:
    portfolio_root = tmp_path / "portfolio"
    portfolio_root.mkdir(parents=True)
    path = portfolio_root / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    store = PortfolioStore(tmp_path)

    report = store.migrate_to_v2(dry_run=False)

    assert report["migrated"] == []
    assert report["errors"][0]["id"] == "broken"
    assert path.read_text(encoding="utf-8") == "{broken"


def test_detail_file_wins_when_index_metadata_conflicts(tmp_path) -> None:
    portfolio_root = tmp_path / "portfolio"
    portfolio_root.mkdir(parents=True)
    (portfolio_root / "p1.json").write_text(
        json.dumps(
            {
                "version": 2,
                "id": "p1",
                "name": "Detail Name",
                "pinned": True,
                "holdings": [],
            }
        ),
        encoding="utf-8",
    )
    (portfolio_root / "index.json").write_text(
        json.dumps(
            {
                "version": 2,
                "portfolios": [{"id": "p1", "name": "Stale Index Name", "pinned": False}],
            }
        ),
        encoding="utf-8",
    )

    row = PortfolioStore(tmp_path).list_index_rows()[0]

    assert row["name"] == "Detail Name"
    assert row["pinned"] is True
