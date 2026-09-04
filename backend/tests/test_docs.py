"""交付文档自测:docs 与演示素材的存在性/完整性/格式校验(交付前最后一道闸)。

- docs/api.md:接口文档关键章节齐全(开放平台、扣费铁律、错误码表、TODO);
- backend/README.md:快速启动、.env 变量表、常见问题;
- docs/打包清单-成员2.md:产物名与排除项红线;
- docs/model-config-final.json:合法 JSON,4 个模型;
- backend/assets/samples:manifest.json(3 文本 + 4 图像 + 音视频兜底)与 PNG 魔数。
"""
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


def _read(rel: str) -> str:
    return (REPO_DIR / rel).read_text(encoding="utf-8")


# ---------- docs/api.md ----------

def test_api_md_exists_and_key_sections():
    text = _read("docs/api.md")
    for keyword in (
        "统一返回结构",            # 0.1
        "错误码列表",              # 0.2
        "GET /api/health",         # 1
        "GET /api/models",         # 2
        "POST /api/admin/models",  # 3
        "POST /api/chat/sessions", # 4
        "POST /api/tasks/text",    # 5
        "POST /api/uploads",       # 6
        "/api/chat/completions",   # 7 开放平台
        "chat.completion.chunk",   # 流式帧
        "[DONE]",
        "缺少API Key",             # 开放平台 401 文案
        "请求过于频繁",             # 429 文案
        "扣费铁律",                # 附录 A
        "Mock",                    # 附录 B
        "TODO",                    # 附录 C
    ):
        assert keyword in text, f"docs/api.md 缺少关键内容: {keyword}"


def test_api_md_documents_open_platform_contract():
    text = _read("docs/api.md")
    assert "Bearer sk-" in text
    assert "OPENAPI_RATE_LIMIT_PER_MIN" in text
    assert "冻结" in text and "结算" in text and "释放" in text
    assert "成员4" in text  # Key 管理接口归属说明(未就绪前手工造 Key)


# ---------- backend/README.md ----------

def test_backend_readme_key_sections():
    text = _read("backend/README.md")
    for keyword in (
        "快速启动",
        "uvicorn app.main:app",
        "pytest tests",
        "DATABASE_URL",
        "SECRET_KEY",
        "SILICONFLOW_API_KEY",
        "OPENAPI_RATE_LIMIT_PER_MIN",
        "常见问题",
        "API Key 无效",
    ):
        assert keyword in text, f"backend/README.md 缺少关键内容: {keyword}"


# ---------- docs/打包清单-成员2.md ----------

def test_packaging_checklist():
    text = _read("docs/打包清单-成员2.md")
    assert "成员2-源代码.zip" in text
    assert "Compress-Archive" in text          # PowerShell 命令
    assert "zip -r" in text                     # bash 命令
    for excluded in (".venv", "__pycache__", "uploads", "backend/tests"):
        assert excluded in text, f"打包清单缺少排除项: {excluded}"
    assert "冒烟清单" in text


# ---------- docs/model-config-final.json ----------

def test_model_config_final_json():
    data = json.loads(_read("docs/model-config-final.json"))
    models = data["models"]
    assert len(models) == 9
    codes = {m["model_code"] for m in models}
    assert "Qwen/Qwen2.5-7B-Instruct" in codes
    vendors = {m["vendor"] for m in models}
    assert vendors <= {"siliconflow", "ollama", "dashscope", "mock"}
    for m in models:
        assert m["provider_type"] in ("online", "local")
        assert m["model_type"] in ("text", "image", "audio", "video")
        assert isinstance(m["price_per_call"], int) and m["price_per_call"] >= 0
        assert m["status"] in ("enabled", "disabled")
        # 密钥绝不入配置文件
        assert "api_key" not in json.dumps(m).lower()


# ---------- backend/assets/samples ----------

def test_samples_manifest():
    manifest = json.loads(_read("backend/assets/samples/manifest.json"))
    assert len(manifest["text_samples"]) == 3
    for s in manifest["text_samples"]:
        assert s["messages"] and s["messages"][0]["role"] in ("user", "system")
    images = manifest["image_samples"]
    assert len(images) == 4
    fallback = manifest["audio_video_fallback"]
    assert fallback["audio_url"].startswith("http")
    assert fallback["video_url"].startswith("http")


def test_sample_images_are_valid_png():
    for i in range(1, 5):
        path = BACKEND_DIR / "assets" / "samples" / f"sample-image-{i}.png"
        assert path.exists(), f"缺少演示图 {path.name}"
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} 不是合法 PNG"
