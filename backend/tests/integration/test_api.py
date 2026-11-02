"""End-to-end API tests against the assembled application (fake adapters)."""

from __future__ import annotations

from lightpanel.domain.models import CommandResult


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["env"] == "dev"


def test_system_snapshot(client):
    response = client.get("/api/system")
    assert response.status_code == 200
    body = response.json()
    assert body["host"]["hostname"] == "lightpanel-demo"
    assert 0 <= body["cpu"]["percent"] <= 100
    assert body["memory"]["total_human"].endswith("GB")
    assert len(body["disks"]) == 2


def test_system_history(client):
    client.get("/api/system")
    history = client.get("/api/system/history").json()
    assert isinstance(history, list)
    assert {"timestamp", "cpu_percent", "memory_percent"} <= set(history[-1])


def test_system_invalidate(client):
    assert client.post("/api/system/invalidate").json() == {"ok": True}


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
def test_catalog_is_seeded_empty_in_memory_mode(client):
    assert client.get("/api/catalog").json()["entries"] == []


def test_catalog_crud_flow(client):
    created = client.post(
        "/api/catalog/entries",
        json={"name": "Grafana", "url": "https://grafana.local", "tags": ["监控", "ops"]},
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert entry_id == "grafana"

    fetched = client.get(f"/api/catalog/entries/{entry_id}")
    assert fetched.json()["name"] == "Grafana"

    updated = client.put(
        f"/api/catalog/entries/{entry_id}", json={"name": "Grafana", "tags": ["监控"]}
    )
    assert updated.json()["tags"] == ["监控"]

    assert client.delete(f"/api/catalog/entries/{entry_id}").status_code == 204
    assert client.get(f"/api/catalog/entries/{entry_id}").status_code == 404


def test_catalog_duplicate_is_conflict(client):
    client.post("/api/catalog/entries", json={"name": "Dup", "url": "https://d.local"})
    response = client.post("/api/catalog/entries", json={"name": "Dup", "url": "https://d.local"})
    assert response.status_code == 409


def test_catalog_validation_error(client):
    response = client.post("/api/catalog/entries", json={"name": "x", "url": "ftp://bad"})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_catalog_request_validation_error(client):
    response = client.post("/api/catalog/entries", json={"url": "https://x"})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_catalog_tag_filter_and_summary(client):
    client.post("/api/catalog/entries", json={"name": "A", "url": "https://a", "tags": ["ops", "x"]})
    client.post("/api/catalog/entries", json={"name": "B", "url": "https://b", "tags": ["ops"]})
    client.post("/api/catalog/entries", json={"name": "C", "url": "https://c", "tags": ["y"]})

    body = client.get("/api/catalog", params={"tags": "ops"}).json()
    assert body["total"] == 2
    assert body["tags"][0] == {"name": "ops", "count": 2}

    body = client.get("/api/catalog", params={"tags": "ops,y", "match_all": "true"}).json()
    assert body["total"] == 0


def test_catalog_set_tags_and_reorder(client):
    first = client.post("/api/catalog/entries", json={"name": "A", "url": "https://a"}).json()["id"]
    second = client.post("/api/catalog/entries", json={"name": "B", "url": "https://b"}).json()["id"]

    assert client.put(f"/api/catalog/entries/{first}/tags", json={"tags": ["z"]}).json()["tags"] == ["z"]
    ordered = client.post("/api/catalog/reorder", json={"ids": [second, first]}).json()
    assert [e["id"] for e in ordered] == [second, first]


# --------------------------------------------------------------------------- #
# Docker
# --------------------------------------------------------------------------- #
def test_container_status(client):
    body = client.get("/api/containers/status").json()
    assert body == {"provider": "fake", "available": True, "total": 4, "running": 3, "stopped": 1}


def test_container_list_and_filters(client):
    names = [c["name"] for c in client.get("/api/containers").json()]
    assert set(names) == {"lightpanel-web", "postgres", "redis", "nginx"}
    assert [c["name"] for c in client.get("/api/containers", params={"state": "exited"}).json()] == [
        "redis"
    ]
    assert len(client.get("/api/containers", params={"include_stopped": "false"}).json()) == 3


def test_container_lifecycle(client):
    response = client.post("/api/containers/redis/start")
    assert response.status_code == 200
    assert response.json()["container"]["state"] == "running"

    response = client.post("/api/containers/redis/stop", json={"timeout": 5})
    assert response.json()["container"]["state"] == "exited"


def test_container_unknown_action(client):
    response = client.post("/api/containers/redis/explode")
    assert response.status_code == 400


def test_container_not_found(client):
    assert client.get("/api/containers/ghost").status_code == 404


def test_container_logs(client):
    body = client.get("/api/containers/nginx/logs", params={"tail": 5}).json()
    assert body["tail"] == 5
    assert "nginx" in body["content"]


def test_stack_list(client):
    stacks = {s["name"]: s for s in client.get("/api/stacks").json()}
    assert stacks["lightpanel"]["status"] == "running"
    assert stacks["cache"]["status"] == "stopped"
    assert stacks["lightpanel"]["total"] == 2


def test_stack_action(client):
    # restart 走项目标签，不依赖 compose 文件是否存在
    response = client.post("/api/stacks/lightpanel/restart", json={"extra_args": ["--force-recreate"]})
    assert response.status_code == 200
    body = response.json()
    assert body["stack"]["name"] == "lightpanel"
    assert body["result"]["argv"][-1] == "--force-recreate"


def test_stack_action_failure_is_reported(app, client):
    app.state.container.command_executor.always(
        CommandResult.failure(("docker", "compose", "restart"), 1, stderr="boom")
    )
    response = client.post("/api/stacks/lightpanel/restart", json={})
    assert response.status_code == 502
    assert response.json()["code"] == "command_failed"
    assert "boom" in response.json()["details"]["stderr"]


def test_stack_up_without_reachable_compose_files_is_rejected(client):
    """fake 引擎里的栈配置在 /opt/lightpanel，本机读不到，up 应当 400 而不是 502。"""
    response = client.post("/api/stacks/lightpanel/up", json={})
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "validation_error"
    assert "lightpanel" in payload["message"]


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def test_commands_listing(client):
    ids = {c["id"] for c in client.get("/api/commands").json()}
    assert {"container.start", "container.stop", "stack.up"} <= ids


def test_commands_listing_by_target(client):
    ids = {c["id"] for c in client.get("/api/commands", params={"target": "stack"}).json()}
    assert ids == {"stack.up", "stack.down", "stack.restart", "stack.pull"}


def test_run_builtin_command(client):
    response = client.post("/api/commands/container.start/run", json={"target_id": "redis"})
    assert response.status_code == 200
    assert response.json()["exit_code"] == 0
    assert client.get("/api/containers/redis").json()["state"] == "running"


def test_run_unknown_command(client):
    assert client.post("/api/commands/nope/run", json={}).status_code == 404


def test_ad_hoc_command_is_rejected_by_policy(client):
    response = client.post("/api/commands/run-adhoc", json={"argv": ["rm", "-rf", "/"]})
    assert response.status_code == 400
    assert response.json()["code"] == "command_rejected"


def test_ad_hoc_command_runs(client, app):
    app.state.container.command_executor.always(
        CommandResult.success(("docker", "ps"), stdout="CONTAINER ID")
    )
    response = client.post("/api/commands/run-adhoc", json={"argv": ["docker", "ps"]})
    assert response.status_code == 200
    assert "CONTAINER" in response.json()["stdout"]


def test_ad_hoc_command_with_context(client, app):
    app.state.container.command_executor.always(CommandResult.success(("docker",), stdout="ok"))
    response = client.post(
        "/api/commands/run-adhoc",
        json={"argv": ["docker", "logs", "{name}"], "context": {"name": "nginx"}},
    )
    assert response.status_code == 200
    assert app.state.container.command_executor.last_argv == ("docker", "logs", "nginx")
