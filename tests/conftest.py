from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        demo_enabled=True,
        dashscope_api_key="",
        amap_api_key="",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def create_session(client: TestClient):
    response = client.post("/api/sessions")
    assert response.status_code == 201
    return response.json()
