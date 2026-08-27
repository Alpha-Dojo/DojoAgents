from __future__ import annotations

from types import SimpleNamespace


def test_sector_return_curve_route_ok(financial_client, monkeypatch) -> None:
    async def _fake_build(*_args, **_kwargs):
        from dojoagents.dashboard.schemas.domain_api import SectorReturnCurveResponse

        return SectorReturnCurveResponse(
            level1_id="1",
            level2_id="2",
            level3_id="3",
            market="us",
            start_date="2026-01-01",
            end_date="2026-01-05",
            window_start="2026-01-02",
            window_end="2026-01-05",
            cumulative_return_pct=1.5,
            points=[],
        )

    monkeypatch.setattr(
        "dojoagents.dashboard.routers.sector.resolve_sector_analysis_path",
        lambda *_a, **_k: SimpleNamespace(level1_id="1", level2_id="2", level3_id="3"),
    )
    monkeypatch.setattr(
        "dojoagents.dashboard.routers.sector.build_sector_return_curve_v1",
        _fake_build,
    )

    response = financial_client.get(
        "/api/v1/sector/return-curve"
        "?level1_id=1&level2_id=2&level3_id=3&market=us&start_date=2026-01-01&end_date=2026-01-05"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["cumulative_return_pct"] == 1.5
    assert payload["market"] == "us"


def test_sector_return_curve_route_404_when_path_missing(financial_client, monkeypatch) -> None:
    monkeypatch.setattr(
        "dojoagents.dashboard.routers.sector.resolve_sector_analysis_path",
        lambda *_a, **_k: None,
    )
    response = financial_client.get(
        "/api/v1/sector/return-curve"
        "?level1_id=1&level2_id=2&level3_id=3&market=us&start_date=2026-01-01&end_date=2026-01-05"
    )
    assert response.status_code == 404
