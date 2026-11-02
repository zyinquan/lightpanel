"""SPA 静态托管：history 路由回退行为。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lightpanel.api.app import SPAStaticFiles


@pytest.fixture()
def spa_app(tmp_path: Path) -> FastAPI:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=str(dist), api_prefix="/api"), name="frontend")
    return app


def test_deep_link_falls_back_to_index(spa_app: FastAPI) -> None:
    client = TestClient(spa_app)
    for path in ("/", "/containers", "/stacks/demo", "/catalog"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "SPA" in response.text


def test_real_asset_is_served(spa_app: FastAPI) -> None:
    response = TestClient(spa_app).get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log" in response.text


def test_missing_asset_stays_404(spa_app: FastAPI) -> None:
    # 缺文件时返回 HTML 会把前端的 404 藏起来，这里必须保持 404
    assert TestClient(spa_app).get("/assets/missing.js").status_code == 404


def test_api_prefix_is_not_spa_fallback(spa_app: FastAPI) -> None:
    client = TestClient(spa_app)
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/api").status_code == 404
