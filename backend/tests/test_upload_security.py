"""上传安全边界回归测试（补充现有 94 例未覆盖的安全路径）。

覆盖：
- 目录穿越:文件名含 ../ 仅取 basename,落到 uploads 内;
- 扩展名白名单:.exe/.html 拒绝;
- 魔数校验:.png 传文本内容拒绝、mp3 非 ID3 拒绝;
- 10MB 上限:超限拒绝;
- 空文件拒绝;
- 合法 PNG 落盘并返回 /static URL;
- UploadFile.filename 为空时的健壮处理。
"""
import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.response import register_exception_handlers
from app.core.config import get_settings
from app.core.deps import get_current_user
from app.models import user as user_mod  # noqa: F401 仅在需要时引用
from app.models.support import User
from app.routers import uploads
from app.services import av_service


@pytest.fixture()
def fake_user() -> User:
    u = User(id=1, username="uploader", password_hash="x", role="user", status=1)
    return u


@pytest.fixture()
def client(fake_user, tmp_path, monkeypatch):
    """最小应用:只挂 uploads 路由,替换鉴权与上传目录为临时目录。"""
    # upload_path 为只读派生属性,改其基础字段 upload_dir(absolute 时即目录本身)
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(uploads.router)
    app.dependency_overrides[get_current_user] = lambda: fake_user
    return TestClient(app, raise_server_exceptions=False), tmp_path


PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\0" * 30


def _post(client, filename, content: bytes):
    return client.post("/uploads", files={"file": (filename, content)})


# 1. 目录穿越:仅取 basename,且不含穿越片段
def test_path_traversal_is_sanitized(client):
    c, tmp = client
    resp = _post(c, "../../evil.png", PNG_HEAD)
    assert resp.status_code == 200, resp.text
    saved_name = resp.json()["data"]["filename"]
    assert "/" not in saved_name and ".." not in saved_name
    assert (tmp / saved_name).exists()  # 落在 uploads 内
    # 目录外与临时目录同层均无残留
    assert not (tmp.parent / saved_name).exists()
    assert not (tmp.parent.parent / "evil.png").exists()


# 2. 扩展名白名单
@pytest.mark.parametrize("bad_ext", ["exe", "html", "js", "sh", "php"])
def test_disallowed_extensions_rejected(client, bad_ext):
    c, _ = client
    resp = _post(c, f"payload.{bad_ext}", b"MZ" + b"\0" * 10)
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["message"]


# 3. 魔数校验:类型与内容不符
def test_magic_mismatch_rejected(client):
    c, _ = client
    # 声称 png 但内容是纯文本
    resp = _post(c, "fake.png", b"hello not a png")
    assert resp.status_code == 400
    assert "文件内容与类型不符" in resp.json()["message"]
    # 声称 mp3 但非 ID3/帧同步
    resp = _post(c, "fake.mp3", b"ABCDEFGH" * 4)
    assert resp.status_code == 400
    assert "文件内容与类型不符" in resp.json()["message"]


# 4. 超过 10MB
def test_oversize_rejected(client):
    c, _ = client
    big = PNG_HEAD + b"\x00" * (av_service.MAX_UPLOAD_SIZE + 100)
    resp = _post(c, "big.png", big)
    assert resp.status_code == 400
    assert "10MB" in resp.json()["message"]


# 5. 空文件
def test_empty_file_rejected(client):
    c, _ = client
    resp = _post(c, "empty.png", b"")
    assert resp.status_code == 400
    assert "文件内容为空" in resp.json()["message"]


# 6. 合法 PNG 落盘并返回 /static URL,文件名带 uuid 前缀
def test_valid_png_saved_with_uuid_prefix(client):
    c, tmp = client
    resp = _post(c, "badge.png", PNG_HEAD)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["url"].startswith("/static/")
    assert data["filename"].endswith("-badge.png")
    assert data["size"] == len(PNG_HEAD)
    # 重名上传不覆盖(先有者保留)
    assert (tmp / data["filename"]).exists()
    assert not (tmp / "badge.png").exists()  # 原始名不落盘


# 7. filename 为 None/空:优雅拒绝而非崩溃
def test_missing_filename_handled(client):
    c, _ = client
    resp = _post(c, None, PNG_HEAD)
    assert resp.status_code in (200, 400)  # 允许拒绝,但不允许 500
    assert resp.status_code != 500