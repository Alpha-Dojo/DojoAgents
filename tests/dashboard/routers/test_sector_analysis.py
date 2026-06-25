from __future__ import annotations

import dojoagents.dashboard.routers.sector as sector_router


def test_sector_analysis_returns_404_when_path_cannot_be_resolved(financial_client, monkeypatch) -> None:
    monkeypatch.setattr(sector_router, "resolve_sector_analysis_path", lambda *_args, **_kwargs: None)

    response = financial_client.get("/api/v1/sector/analysis?level1_id=1&level2_id=2&level3_id=3")

    assert response.status_code == 404
    assert response.json() == {"detail": "unknown sector path: 1/2/3"}


def test_sector_analysis_response_omits_internal_scopes_field(financial_client) -> None:
    response = financial_client.get("/api/v1/sector/analysis?level1_id=1&level2_id=2&level3_id=3")

    assert response.status_code == 200
    assert "scopes" not in response.json()
