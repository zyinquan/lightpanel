"""Catalog icon upload & lifecycle through the HTTP API."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24


def _create_entry(client: TestClient, **overrides) -> dict:
    payload = {"name": "Jellyfin", "url": "http://media.local", **overrides}
    response = client.post("/api/catalog/entries", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_serve_and_reference(client):
    response = client.post("/api/catalog/icons", content=PNG, headers={"Content-Type": "image/png"})
    assert response.status_code == 201, response.text
    url = response.json()["url"]
    assert re.fullmatch(r"/api/catalog/icons/[0-9a-f]{16}\.png", url)

    served = client.get(url)
    assert served.status_code == 200
    assert served.content == PNG
    assert "immutable" in served.headers["cache-control"]

    _create_entry(client, icon_image=url)
    listed = client.get("/api/catalog").json()["entries"][0]
    assert listed["icon_image"] == url


def test_replacing_icon_removes_orphan_file_but_keeps_shared_one(client):
    first = client.post("/api/catalog/icons", content=PNG).json()["url"]
    second = client.post("/api/catalog/icons", content=JPEG).json()["url"]
    entry = _create_entry(client, icon_image=first)

    # 换图：旧文件没人引用了，应该被清掉
    updated = client.put(
        f"/api/catalog/entries/{entry['id']}", json={**entry, "icon_image": second}
    ).json()
    assert updated["icon_image"] == second
    assert client.get(first).status_code == 404
    assert client.get(second).status_code == 200

    # 两个条目共用一张图时，只改一个不能删文件
    other = _create_entry(client, name="Emby", url="http://emby.local", icon_image=second)
    client.put(f"/api/catalog/entries/{entry['id']}", json={**entry, "icon_image": ""})
    assert client.get(second).status_code == 200

    # 删掉最后一个引用者后文件才消失
    client.delete(f"/api/catalog/entries/{other['id']}")
    assert client.get(second).status_code == 404


def test_upload_rejects_bad_content(client):
    assert client.post("/api/catalog/icons", content=b"").status_code == 400
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    assert client.post("/api/catalog/icons", content=svg).status_code == 400
    assert client.get("/api/catalog/icons/nope.png").status_code == 404


def test_entry_rejects_bad_icon_image_reference(client):
    response = client.post(
        "/api/catalog/entries",
        json={"name": "Bad", "url": "http://x.local", "icon_image": "javascript:alert(1)"},
    )
    assert response.status_code == 400
