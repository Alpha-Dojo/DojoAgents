from unittest.mock import MagicMock, patch

from dojoagents.cli.model_setup import probe_endpoint_models


def test_probe_endpoint_models_adds_extra_headers() -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": [{"id": "gpt-4.1"}]}

    with patch("dojoagents.cli.model_setup.httpx.get", return_value=response) as get:
        models = probe_endpoint_models(
            "https://api.example.test/v1",
            "api-key",
            {"X-Tenant-ID": "tenant-42"},
        )

    assert models == ["gpt-4.1"]
    assert get.call_args.kwargs["headers"] == {
        "X-Tenant-ID": "tenant-42",
        "Authorization": "Bearer api-key",
    }


def test_probe_endpoint_models_preserves_explicit_authorization_header() -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": []}

    with patch("dojoagents.cli.model_setup.httpx.get", return_value=response) as get:
        probe_endpoint_models(
            "https://api.example.test/v1",
            "api-key",
            {"Authorization": "Bearer proxy-key"},
        )

    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer proxy-key"
