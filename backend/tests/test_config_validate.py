import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


def _mock_llm(model_id="gpt-4o"):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(
        response_metadata={"model_name": model_id}
    ))
    return llm


def _mock_openai_models(ids: list):
    mock_client = MagicMock()
    mock_list = MagicMock()
    mock_list.data = [MagicMock(id=m) for m in ids]
    mock_client.models.list = AsyncMock(return_value=mock_list)
    return mock_client


def test_validate_returns_sorted_models_on_success():
    model_ids = ["gpt-4o-mini", "gpt-4o", "whisper-1"]
    with (
        patch("api.routes.config.get_llm", return_value=_mock_llm()),
        patch("api.routes.config.AsyncOpenAI", return_value=_mock_openai_models(model_ids)),
    ):
        resp = client.post("/api/config/validate", json={"model": "gpt-4o", "api_key": "sk-x", "base_url": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["models"] == sorted(model_ids)


def test_validate_returns_none_models_when_listing_fails():
    mock_client = MagicMock()
    mock_client.models.list = AsyncMock(side_effect=Exception("permission denied"))
    with (
        patch("api.routes.config.get_llm", return_value=_mock_llm()),
        patch("api.routes.config.AsyncOpenAI", return_value=mock_client),
    ):
        resp = client.post("/api/config/validate", json={"model": "gpt-4o", "api_key": "sk-x", "base_url": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["models"] is None


def test_validate_returns_null_models_on_validation_failure():
    with patch("api.routes.config.get_llm", side_effect=Exception("bad key")):
        resp = client.post("/api/config/validate", json={"model": "gpt-4o", "api_key": "sk-bad", "base_url": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["models"] is None
