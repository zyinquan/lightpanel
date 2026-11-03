"""Authentication behaviour."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lightpanel.api.app import create_app
from lightpanel.config import load_config


@pytest.fixture
def secured_config():
    return load_config(
        overrides={
            "security": {"enabled": True, "api_token": "s3cret"},
            "docker": {"mode": "fake"},
            "catalog": {"provider": "memory"},
            "metrics": {"provider": "fake", "cache_ttl": 0},
            "commands": {"extra_file": "__missing__.yaml"},
        }
    )


@pytest.fixture
def secured_client(secured_config):
    with TestClient(create_app(config=secured_config)) as client:
        yield client


def test_public_endpoints_are_open(secured_client):
    assert secured_client.get("/api/health").status_code == 200
    assert secured_client.get("/api/auth/status").json() == {"enabled": True, "authenticated": False}


def test_protected_endpoint_requires_token(secured_client):
    response = secured_client.get("/api/containers")
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_header_token_works(secured_client):
    response = secured_client.get("/api/containers", headers={"X-LightPanel-Token": "s3cret"})
    assert response.status_code == 200


def test_query_token_works(secured_client):
    assert secured_client.get("/api/containers", params={"token": "s3cret"}).status_code == 200


def test_wrong_token_is_rejected(secured_client):
    assert secured_client.get("/api/containers", headers={"X-LightPanel-Token": "bad"}).status_code == 401


def test_login_sets_cookie(secured_client):
    response = secured_client.post("/api/auth/login", json={"token": "s3cret"})
    assert response.json()["ok"] is True
    assert "lightpanel_token" in secured_client.cookies
    assert secured_client.get("/api/containers").status_code == 200


def test_login_reports_authenticated(secured_client):
    """前端拿这个返回值决定退出登录页；只给 ok/enabled 会卡在登录页。"""
    body = secured_client.post("/api/auth/login", json={"token": "s3cret"}).json()
    assert body["enabled"] is True
    assert body["authenticated"] is True


def test_status_reflects_cookie(secured_client):
    secured_client.post("/api/auth/login", json={"token": "s3cret"})
    body = secured_client.get("/api/auth/status").json()
    assert body == {"enabled": True, "authenticated": True}


def test_status_reflects_header(secured_client):
    body = secured_client.get("/api/auth/status", headers={"X-LightPanel-Token": "s3cret"}).json()
    assert body == {"enabled": True, "authenticated": True}


def test_status_rejects_wrong_header(secured_client):
    body = secured_client.get("/api/auth/status", headers={"X-LightPanel-Token": "bad"}).json()
    assert body == {"enabled": True, "authenticated": False}


def test_login_with_bad_token(secured_client):
    response = secured_client.post("/api/auth/login", json={"token": "nope"})
    assert response.status_code == 401


def test_logout_clears_cookie(secured_client):
    secured_client.post("/api/auth/login", json={"token": "s3cret"})
    secured_client.post("/api/auth/logout")
    assert secured_client.get("/api/containers").status_code == 401


def test_disabled_auth_allows_everything(client):
    # With protection off every request counts as authenticated.
    assert client.get("/api/auth/status").json() == {"enabled": False, "authenticated": True}
    assert client.get("/api/containers").status_code == 200


def test_missing_token_configuration_disables_protection():
    config = load_config(
        overrides={
            "security": {"enabled": True, "api_token": ""},
            "docker": {"mode": "fake"},
            "catalog": {"provider": "memory"},
            "commands": {"extra_file": "__missing__.yaml"},
        }
    )
    with TestClient(create_app(config=config)) as anonymous:
        assert anonymous.get("/api/containers").status_code == 200


def test_change_password_requires_current(secured_client):
    response = secured_client.post(
        "/api/auth/password", json={"current": "wrong", "new": "newpass1"}
    )
    assert response.status_code == 401


def test_change_password_takes_effect_immediately(secured_client):
    secured_client.post(
        "/api/auth/password", json={"current": "s3cret", "new": "newpass1"}
    )
    secured_client.cookies.clear()  # 去掉响应刚写入的新 cookie，逐项验证
    assert secured_client.get("/api/containers").status_code == 401
    assert (
        secured_client.get("/api/containers", headers={"X-LightPanel-Token": "s3cret"}).status_code
        == 401
    )
    body = secured_client.get(
        "/api/auth/status", headers={"X-LightPanel-Token": "newpass1"}
    ).json()
    assert body == {"enabled": True, "authenticated": True}


def test_change_password_validates_input(secured_client):
    too_short = secured_client.post(
        "/api/auth/password", json={"current": "s3cret", "new": "123"}
    )
    assert too_short.status_code == 422  # pydantic min_length

    same = secured_client.post(
        "/api/auth/password", json={"current": "s3cret", "new": "s3cret"}
    )
    assert same.status_code == 400


def test_change_password_persists_to_config_file(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "security:\n  enabled: true\n  api_token: oldpass1\nserver:\n  port: 9000\n",
        encoding="utf-8",
    )
    config = load_config(str(config_file))
    with TestClient(create_app(config=config)) as tc:
        tc.post("/api/auth/password", json={"current": "oldpass1", "new": "newpass1"})

    import yaml

    saved = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert saved["security"]["api_token"] == "newpass1"
    assert saved["server"]["port"] == 9000  # 其余键不动
    assert not list(tmp_path.glob("*.tmp"))


def test_change_password_rejected_when_auth_disabled(client):
    response = client.post(
        "/api/auth/password", json={"current": "x", "new": "newpass1"}
    )
    assert response.status_code == 400
    assert "未启用鉴权" in response.json()["message"]


def test_usage_endpoint_is_under_auth(secured_client):
    assert secured_client.get("/api/containers/usage").status_code == 401
