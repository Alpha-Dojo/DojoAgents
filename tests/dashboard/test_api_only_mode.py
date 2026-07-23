from types import SimpleNamespace

from fastapi.testclient import TestClient

from dojoagents.dashboard.server import create_app


def test_api_only_dashboard_keeps_financial_api_and_disables_agent_routes():
    services = SimpleNamespace(
        registry=SimpleNamespace(),
        market_data_revision={},
    )
    app = create_app(
        runtime=None,
        app_services=services,
        app_services_owned=False,
        agent_enabled=False,
    )

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        assert "/api/v1/market/overview" in schema["paths"]
        assert "/api/v1/portfolio" in schema["paths"]

        response = client.post("/api/chat", json={})
        assert response.status_code == 503
        assert response.json()["code"] == "agent_runtime_disabled"
