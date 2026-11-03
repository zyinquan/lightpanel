"""IconStore: uploaded icon files on disk."""

from __future__ import annotations

import pytest

from lightpanel.adapters.catalog.icon_store import IconStore
from lightpanel.domain.errors import ValidationError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture
def store(tmp_path) -> IconStore:
    return IconStore(tmp_path / "icons")


async def test_save_png_returns_managed_url(store):
    url = await store.save(PNG)
    assert store.is_managed(url)
    assert url.startswith("/api/catalog/icons/")
    assert url.endswith(".png")
    path = store.resolve(url)
    assert path is not None and path.read_bytes() == PNG


async def test_save_detects_format_from_magic_bytes_not_client_name(store):
    url = await store.save(JPEG)
    assert url.endswith(".jpg")


async def test_save_rejects_empty_oversize_and_unknown(store):
    with pytest.raises(ValidationError):
        await store.save(b"")
    small = IconStore(store.root, max_bytes=10)
    with pytest.raises(ValidationError):
        await small.save(PNG)
    # SVG / 文本一律拒绝：SVG 可内嵌脚本，不做上传目标
    with pytest.raises(ValidationError):
        await store.save(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    with pytest.raises(ValidationError):
        await store.save(b"not-an-image-at-all")


async def test_resolve_rejects_path_traversal_and_garbage(store):
    await store.save(PNG)
    assert store.resolve("../../etc/passwd") is None
    assert store.resolve("/api/catalog/icons/nope.png") is None
    assert store.resolve("zzzz") is None
    # 存在但扩展名不在白名单
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / "aabbccddeeff0011.svg").write_bytes(b"<svg/>")
    assert store.resolve("aabbccddeeff0011.svg") is None


async def test_delete_removes_file_and_tolerates_missing(store):
    url = await store.save(PNG)
    path = store.resolve(url)
    assert path is not None
    await store.delete(url)
    assert not path.exists()
    await store.delete(url)  # 幂等
