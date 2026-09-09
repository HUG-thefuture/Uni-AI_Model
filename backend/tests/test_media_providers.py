"""媒体任务媒体通路回归测试(图生图 / 声音克隆 / schema 校验,不触真实上游)。

覆盖:
- ImageTaskCreate.image_url 校验与自动并入 params(routers 零改动透传);
- Mock 图生图端到端:HTTP 提交 → 后台执行 → succeeded 且结果含参考图本身;
- Mock 声音克隆带 sample:raw 带 voice_clone 标记;执行器链路 result_url 落 /static/;
- DashScope 图生图原协议:仅 monkeypatch,验证提交 body 的 input.base_image_url
  与轮询调用,绝不发真网请求;文生图模型带参考图给明确中文错误;
- OnlineProvider(硅基流动)图生图 /v1/image/edit 与两步声音克隆:桩 client。
"""
import asyncio
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_DB_FILE = Path(tempfile.gettempdir()) / "uni_ai_model_test1_media.db"
if _DB_FILE.exists():
    _DB_FILE.exists() and _DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-bytes-long"
# Provider 层单测用的假密钥(仅防「未配置」报错;所有用例均不发真网请求)
os.environ["DASHSCOPE_API_KEY"] = "test-dashscope-key"
os.environ["SILICONFLOW_API_KEY"] = "test-siliconflow-key"
# 生成的媒体产物落临时目录,避免污染仓库 uploads/
_UPLOAD_ROOT = Path(tempfile.mkdtemp(prefix="uni_ai_media_"))
os.environ["UPLOAD_DIR"] = str(_UPLOAD_ROOT / "uploads")

from pydantic import ValidationError  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal, async_engine, engine, init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.ai_task import AiTask  # noqa: E402
from app.models.model import Model  # noqa: E402
from app.models.user import User, UserProfile, Wallet  # noqa: E402
from app.providers.dashscope import (  # noqa: E402
    IMAGE2IMAGE_SUBMIT_URL,
    IMAGE_SUBMIT_URL,
    DashScopeProvider,
)
from app.providers.exceptions import ProviderError  # noqa: E402
from app.providers.mock import MockProvider  # noqa: E402
from app.providers.online import BASE_URL, OnlineProvider  # noqa: E402
from app.schemas.task import ImageTaskCreate  # noqa: E402
from app.services import av_service, task_service  # noqa: E402


def _fake_resp(status_code: int = 200, payload: dict | None = None,
               text: str | None = None, content: bytes = b"") -> SimpleNamespace:
    """假 httpx 响应:仅提供 Provider 代码实际访问的属性。"""
    return SimpleNamespace(
        status_code=status_code,
        text=text if text is not None else json.dumps(payload or {}),
        json=lambda: payload if payload is not None else {},
        content=content,
        request=SimpleNamespace(),
    )


class _StubAsyncClient:
    """桩 httpx.AsyncClient:记录 post 调用并按 URL 返回预设假响应(替代真实网络)。"""

    def __init__(self, responder):
        self._responder = responder
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url, **kwargs):
        body = kwargs.get("json") or {}
        self.calls.append((url, body))
        return self._responder(url, body)


class MediaProvidersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_db()
        with SessionLocal() as db:
            user = User(username="media_test", password_hash=hash_password("Media1234"),
                        role="user", status=1, real_auth_status=0)
            db.add(user)
            db.flush()
            db.add_all([
                UserProfile(user_id=user.id, nickname="media_test"),
                Wallet(user_id=user.id, balance=100, total_recharged=0, total_consumed=0),
            ])
            # mock_delay_sec=0:Mock 立即返回,测试不等待随机延迟
            image_model = Model(
                name="Mock 图像", model_code="mock-image-media-test", provider_type="online",
                model_type="image", vendor="mock", price_per_call=0,
                config_json='{"mock_delay_sec": 0}',
            )
            audio_model = Model(
                name="Mock 声音", model_code="mock-audio-media-test", provider_type="online",
                model_type="audio", vendor="mock", price_per_call=0,
                config_json='{"mock_delay_sec": 0}',
            )
            db.add_all([image_model, audio_model])
            db.commit()
            cls.user_id = user.id
            cls.image_model_id = image_model.id
            cls.audio_model_id = audio_model.id
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        # 只清理本类写入的行,不删库文件:同进程后续还会跑其他测试模块,
        # 且 test_model_seed 断言 models 表精确行数,必须移除本类插入的 2 个模型。
        with SessionLocal() as db:
            db.query(AiTask).filter(AiTask.user_id == cls.user_id).delete(synchronize_session=False)
            db.query(Wallet).filter(Wallet.user_id == cls.user_id).delete(synchronize_session=False)
            db.query(UserProfile).filter(UserProfile.user_id == cls.user_id).delete(synchronize_session=False)
            db.query(User).filter(User.id == cls.user_id).delete(synchronize_session=False)
            db.query(Model).filter(Model.id.in_([cls.image_model_id, cls.audio_model_id])).delete(synchronize_session=False)
            db.commit()
        engine.dispose()
        asyncio.run(async_engine.dispose())
        shutil.rmtree(_UPLOAD_ROOT, ignore_errors=True)

    # ---------- 公共辅助 ----------

    def _login(self, client: TestClient) -> str:
        resp = client.post("/api/auth/login", json={"username": "media_test", "password": "Media1234"})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["data"]["token"]

    @staticmethod
    def _auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _wait_terminal(self, task_id: int, timeout: float = 15.0) -> AiTask:
        """轮询 DB 直到任务到终态(succeeded/failed);超时断言失败。"""
        deadline = time.monotonic() + timeout
        last_status = None
        while time.monotonic() < deadline:
            with SessionLocal() as db:
                task = db.get(AiTask, task_id)
                last_status = task.status if task else None
            if last_status in ("succeeded", "failed"):
                return task
            time.sleep(0.1)
        raise AssertionError(f"任务 {task_id} 未在 {timeout}s 内完成,最后状态: {last_status}")

    # ---------- schema 校验 ----------

    def test_image_task_create_schema_image_url(self) -> None:
        """image_url 合法值自动并入 params;javascript: 等伪协议 ValidationError(400 中文提示)。"""
        # 顶层 image_url + 既有 params 合并(其余字段保留)
        body = ImageTaskCreate(model_id=1, prompt="画一只猫", image_url="/static/demo.png",
                               params={"num": 2})
        self.assertEqual(
            body.params.model_dump(exclude_none=True),
            {"num": 2, "image_url": "/static/demo.png"},
        )
        # http(s) 合法;空串 = 不启用图生图
        self.assertEqual(
            ImageTaskCreate(model_id=1, prompt="p", image_url="https://a.com/x.png").image_url,
            "https://a.com/x.png",
        )
        self.assertIsNone(ImageTaskCreate(model_id=1, prompt="p", image_url="  ").image_url)
        # 前端把参考图放进 params 也可,同样受校验
        self.assertEqual(
            ImageTaskCreate(model_id=1, prompt="p",
                            params={"image_url": "http://a.com/x.png"}).params.image_url,
            "http://a.com/x.png",
        )
        # 非法伪协议:顶层与 params 两条路都必须拒绝
        with self.assertRaises(ValidationError):
            ImageTaskCreate(model_id=1, prompt="p", image_url="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            ImageTaskCreate(model_id=1, prompt="p", params={"image_url": "javascript:alert(1)"})

    # ---------- Mock 图生图(端到端) ----------

    def test_mock_image_task_img2img_end_to_end(self) -> None:
        """HTTP 提交图生图任务(顶层 image_url)→ 后台执行 → succeeded 且结果含参考图本身。"""
        with TestClient(app) as client:  # portal 存活:请求返回后后台任务继续执行
            token = self._login(client)
            resp = client.post("/api/tasks/image", headers=self._auth(token), json={
                "model_id": self.image_model_id,
                "prompt": "以图生图:把照片变成动漫风",
                "image_url": "/static/demo.png",
            })
            self.assertEqual(resp.status_code, 200, resp.text)
            data = resp.json()["data"]
            self.assertEqual(data["status"], "pending")
            task = self._wait_terminal(data["task_id"])
        self.assertEqual(task.status, "succeeded", task.error_message)
        urls = json.loads(task.result_url or "[]")
        self.assertIn("/static/demo.png", urls)  # 首图回显参考图,演示以图生图闭环
        # schema 合并链路:image_url 已随 params 落进 ai_tasks.params_json
        self.assertIn("image_url", task.params_json or "")

    def test_image_quantity_billing_charged_by_actual_count(self) -> None:
        """图像计费对齐官方公式「费用=单价×张数」:售价单价 × 实际产出张数精确扣减。

        成本 0.10 元/张 × 加价 130% = 售价 0.13 元/张;请求 3 张 → 冻结 0.39 元,
        Mock 实际返回 3 张 → 结算 0.39 元,余额精确减少 390_000 微元。
        """
        with SessionLocal() as db:
            model = db.get(Model, self.image_model_id)
            model.price_per_call = 0.10
            wallet = db.get(Wallet, self.user_id)
            wallet.balance = 10 * 1_000_000  # ¥10(微元)
            db.commit()
        try:
            with TestClient(app) as client:
                token = self._login(client)
                resp = client.post("/api/tasks/image", headers=self._auth(token), json={
                    "model_id": self.image_model_id,
                    "prompt": "数量计费验证",
                    "params": {"num": 3, "mock_delay_sec": 0},
                })
                self.assertEqual(resp.status_code, 200, resp.text)
                task = self._wait_terminal(resp.json()["data"]["task_id"])
            self.assertEqual(task.status, "succeeded", task.error_message)
            urls = json.loads(task.result_url or "[]")
            self.assertEqual(len(urls), 3)
            self.assertEqual(task.cost, 390_000)  # 0.13 元/张 × 3 = 0.39 元
            self.assertEqual(task.frozen_cost, 390_000)  # 预估 3 张 = 实际 3 张
            with SessionLocal() as db:
                wallet = db.get(Wallet, self.user_id)
                self.assertEqual(wallet.balance, 10 * 1_000_000 - 390_000)
                self.assertEqual(wallet.total_consumed, 390_000)
        finally:
            with SessionLocal() as db:
                model = db.get(Model, self.image_model_id)
                model.price_per_call = 0
                db.commit()

    def test_mock_image_without_image_url_unchanged(self) -> None:
        """无 image_url 时 Mock 行为不变:全部样例图、raw 无 img2img 标记。"""
        model = SimpleNamespace(model_code="mock-image", model_type="image",
                                config_json='{"mock_delay_sec": 0}')
        result = asyncio.run(MockProvider().generate_image(model, "纯文生图"))
        self.assertTrue(all(u.startswith("/static/mock-sample-") for u in result["image_urls"]))
        self.assertNotIn("img2img", result["raw"])
        # 样例图确实落盘且非空(离线可用,不再依赖外网 dummyimage)
        from pathlib import Path
        from app.core.config import get_settings
        for url in result["image_urls"]:
            path = Path(get_settings().upload_dir) / Path(url).name
            self.assertTrue(path.is_file() and path.stat().st_size > 0, url)

    # ---------- Mock 声音克隆带参考音频 ----------

    def test_mock_audio_clone_with_sample(self) -> None:
        """Mock 克隆带 sample:raw 带 voice_clone/sample 标记;执行器链路 result_url 落
        /static/,且 ai_tasks.params_json 保留 voice_clone 标记。"""
        # 1) Provider 层契约:raw 标记
        model = SimpleNamespace(model_code="mock-audio", model_type="audio",
                                config_json='{"mock_delay_sec": 0}')
        result = asyncio.run(MockProvider().generate_audio_clone(model, {
            "voice_name": "alloy", "text": "你好",
            "sample_audio_url": "/static/sample-voice.mp3",
        }))
        self.assertTrue(result["raw"]["voice_clone"])
        self.assertEqual(result["raw"]["sample"], "/static/sample-voice.mp3")

        # 2) 执行器链路:经统一提交通道建任务(params 含 voice_clone 标记 + 参考音频)
        params = {"voice_name": "alloy", "text": "克隆音色试听",
                  "sample_audio_url": "/static/sample-voice.mp3", "voice_clone": True}
        with SessionLocal() as db:
            task = av_service.submit_av_task(
                db, db.get(User, self.user_id), db.get(Model, self.audio_model_id),
                "audio_clone", params["text"], params,
            )
            task_id = task.id
        asyncio.run(task_service.run_async_task(task_id))
        with SessionLocal() as db:
            finished = db.get(AiTask, task_id)
        self.assertEqual(finished.status, "succeeded", finished.error_message)
        self.assertTrue((finished.result_url or "").startswith("/static/"))
        self.assertIn("voice_clone", finished.params_json or "")

    # ---------- DashScope 图生图(monkeypatch,不发真网请求) ----------

    def test_dashscope_img2img_submit_body_and_poll(self) -> None:
        """图生图走 image2image 原协议:提交 body 的 input.base_image_url == 参考图,
        header 带 X-DashScope-Async,并复用 _poll_image_task 轮询与 _download_image 落盘。"""
        provider = DashScopeProvider()
        captured: dict = {}
        submit_resp = _fake_resp(payload={"output": {"task_id": "task-img2img-1"},
                                          "request_id": "req-1"})

        async def fake_post(self, url, *, headers, json_body, model_type, validate=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = json_body
            return submit_resp

        polled: dict = {}

        async def fake_poll(self, task_id, *args, **kwargs):
            polled["task_id"] = task_id
            return {"task_status": "SUCCEEDED",
                    "results": [{"url": "https://oss.example.com/out.png"}]}

        downloaded: dict = {}

        async def fake_download(self, url):
            downloaded["url"] = url
            return "/static/wanx_img2img_out.png"

        model = SimpleNamespace(model_code="wanx-x2img-sketch-turbo", model_type="image")
        settings = get_settings()
        with mock.patch.object(DashScopeProvider, "_post_with_retry", fake_post), \
                mock.patch.object(DashScopeProvider, "_poll_image_task", fake_poll), \
                mock.patch.object(DashScopeProvider, "_download_image", fake_download), \
                mock.patch.object(settings, "dashscope_api_key", "test-dashscope-key"):
            result = asyncio.run(provider.generate_image(
                model, "把背景换成雪山", {"image_url": "https://img.example.com/in.png"},
            ))

        self.assertEqual(captured["url"], IMAGE2IMAGE_SUBMIT_URL)
        self.assertEqual(captured["headers"].get("X-DashScope-Async"), "enable")
        self.assertEqual(captured["body"]["model"], "wanx-x2img-sketch-turbo")
        self.assertEqual(captured["body"]["input"]["base_image_url"],
                         "https://img.example.com/in.png")
        self.assertEqual(captured["body"]["input"]["prompt"], "把背景换成雪山")
        self.assertEqual(polled["task_id"], "task-img2img-1")  # 提交拿句柄后进入轮询
        self.assertEqual(downloaded["url"], "https://oss.example.com/out.png")
        self.assertEqual(result["image_urls"], ["/static/wanx_img2img_out.png"])

    def test_dashscope_t2i_model_rejects_image_url(self) -> None:
        """文生图模型(wanx/t2i)带参考图 → invalid_params 中文提示,不发起任何请求。"""
        provider = DashScopeProvider()
        model = SimpleNamespace(model_code="wanx2.1-t2i-turbo", model_type="image")

        async def unexpected(*args, **kwargs):  # pragma: no cover 不应有网络调用
            raise AssertionError("文生图模型带参考图不应发起上游请求")

        with mock.patch.object(DashScopeProvider, "_post_with_retry", unexpected):
            with self.assertRaises(ProviderError) as ctx:
                asyncio.run(provider.generate_image(
                    model, "p", {"image_url": "/static/in.png"},
                ))
        self.assertEqual(ctx.exception.code, "invalid_params")
        self.assertIn("wanx-x2img", ctx.exception.message_zh)

    def test_dashscope_text2image_path_unchanged(self) -> None:
        """不带 image_url 时仍走 text2image 原协议,body 无 base_image_url。"""
        provider = DashScopeProvider()
        captured: dict = {}

        async def fake_post(self, url, *, headers, json_body, model_type, validate=None):
            captured["url"] = url
            captured["body"] = json_body
            return _fake_resp(payload={"output": {"task_id": "task-t2i-1"}})

        async def fake_poll(self, task_id, *args, **kwargs):
            return {"task_status": "SUCCEEDED",
                    "results": [{"url": "https://oss.example.com/t2i.png"}]}

        async def fake_download(self, url):
            return "/static/wanx_t2i_out.png"

        model = SimpleNamespace(model_code="wanx2.1-t2i-turbo", model_type="image")
        settings = get_settings()
        with mock.patch.object(DashScopeProvider, "_post_with_retry", fake_post), \
                mock.patch.object(DashScopeProvider, "_poll_image_task", fake_poll), \
                mock.patch.object(DashScopeProvider, "_download_image", fake_download), \
                mock.patch.object(settings, "dashscope_api_key", "test-dashscope-key"):
            result = asyncio.run(provider.generate_image(model, "山水画"))
        self.assertEqual(captured["url"], IMAGE_SUBMIT_URL)
        self.assertNotIn("base_image_url", captured["body"]["input"])
        self.assertEqual(result["image_urls"], ["/static/wanx_t2i_out.png"])

    # ---------- OnlineProvider(硅基流动,桩 client) ----------

    def test_online_image_edit_body_and_not_ready(self) -> None:
        """图生图 POST /v1/image/edit(json body 含 image);上游 404 → provider_not_ready
        中文提示(任务失败不扣费)。"""
        provider = OnlineProvider()
        model = SimpleNamespace(model_code="Qwen/Qwen-Image-Edit", model_type="image")
        stub = _StubAsyncClient(
            lambda url, body: _fake_resp(payload={"images": [{"url": "https://oss.example.com/edited.png"}]})
        )
        settings = get_settings()
        with mock.patch("app.core.http_client.get_http_client", return_value=stub), \
                mock.patch.object(settings, "siliconflow_api_key", "test-siliconflow-key"):
            result = asyncio.run(provider.generate_image(
                model, "改成赛博朋克风", {"image_url": "/static/in.png", "image_size": "1024x1024"},
            ))
        url, body = stub.calls[0]
        self.assertTrue(url.endswith("/v1/image/edit"))
        self.assertEqual(body, {
            "model": "Qwen/Qwen-Image-Edit",
            "image": "/static/in.png",
            "prompt": "改成赛博朋克风",
            "image_size": "1024x1024",
        })
        self.assertEqual(result["image_urls"], ["https://oss.example.com/edited.png"])

        # 404 → 明确中文提示,不允许把上游堆栈抛给前端
        stub404 = _StubAsyncClient(
            lambda url, body: _fake_resp(status_code=404, text='{"message":"Not Found"}')
        )
        with mock.patch("app.core.http_client.get_http_client", return_value=stub404), \
                mock.patch.object(settings, "siliconflow_api_key", "test-siliconflow-key"):
            with self.assertRaises(ProviderError) as ctx:
                asyncio.run(provider.generate_image(model, "p", {"image_url": "/static/in.png"}))
        self.assertEqual(ctx.exception.code, "provider_not_ready")
        self.assertIn("图生图", ctx.exception.message_zh)

    def test_online_image_generation_path_unchanged(self) -> None:
        """不带 image_url 时仍走 /v1/images/generations,body 含 batch_size。"""
        provider = OnlineProvider()
        model = SimpleNamespace(model_code="Kwai-Kolors/Kolors", model_type="image")
        stub = _StubAsyncClient(
            lambda url, body: _fake_resp(payload={"images": [{"url": "https://oss.example.com/a.png"}]})
        )
        settings = get_settings()
        with mock.patch("app.core.http_client.get_http_client", return_value=stub), \
                mock.patch.object(settings, "siliconflow_api_key", "test-siliconflow-key"):
            result = asyncio.run(provider.generate_image(model, "一只猫"))
        url, body = stub.calls[0]
        self.assertEqual(url, f"{BASE_URL}/v1/images/generations")
        self.assertNotIn("image", body)
        self.assertEqual(body["batch_size"], 1)
        self.assertEqual(result["image_urls"], ["https://oss.example.com/a.png"])

    def test_online_voice_clone_two_steps(self) -> None:
        """带 sample_audio_url 走两步克隆:先 /v1/uploads/audio/voice 注册音色,
        再以 customName 作为 voice 走 /v1/audio/speech;4xx → voice_clone_failed。"""
        provider = OnlineProvider()
        model = SimpleNamespace(model_code="FunAudioLLM/CosyVoice2-0.5B", model_type="audio")

        def responder(url, body):
            if url.endswith("/v1/uploads/audio/voice"):
                return _fake_resp(payload={"uri": "speech:clone:media-test"})
            return _fake_resp(text="binary-audio", content=b"MP3-BYTES")

        settings = get_settings()
        stub = _StubAsyncClient(responder)
        with mock.patch("app.core.http_client.get_http_client", return_value=stub), \
                mock.patch.object(settings, "siliconflow_api_key", "test-siliconflow-key"):
            result = asyncio.run(provider.generate_audio_clone(model, {
                "text": "你好,克隆一下", "voice_name": "media_voice",
                "sample_audio_url": "/static/ref.mp3",
            }))
        self.assertEqual(len(stub.calls), 2)
        first_url, first_body = stub.calls[0]
        self.assertTrue(first_url.endswith("/v1/uploads/audio/voice"))
        self.assertEqual(first_body, {
            "model": "FunAudioLLM/CosyVoice2-0.5B",
            "customName": "media_voice",
            "audio_url": "/static/ref.mp3",
        })
        second_url, second_body = stub.calls[1]
        self.assertTrue(second_url.endswith("/v1/audio/speech"))
        self.assertEqual(second_body["voice"], "media_voice")  # ② customName 即音色名
        self.assertEqual(second_body["input"], "你好,克隆一下")
        self.assertTrue(result["audio_url"].startswith("/static/"))

        # voice_name 缺省 → customName 用 clone_<时间戳>
        stub_default = _StubAsyncClient(responder)
        with mock.patch("app.core.http_client.get_http_client", return_value=stub_default), \
                mock.patch.object(settings, "siliconflow_api_key", "test-siliconflow-key"):
            asyncio.run(provider.generate_audio_clone(
                model, {"text": "hi", "sample_audio_url": "/static/ref.mp3"},
            ))
        self.assertTrue(stub_default.calls[0][1]["customName"].startswith("clone_"))

        # 上游 4xx → voice_clone_failed(任务失败不扣费)
        stub_bad = _StubAsyncClient(
            lambda url, body: _fake_resp(status_code=400, text='{"message":"invalid audio url"}')
        )
        with mock.patch("app.core.http_client.get_http_client", return_value=stub_bad), \
                mock.patch.object(settings, "siliconflow_api_key", "test-siliconflow-key"):
            with self.assertRaises(ProviderError) as ctx:
                asyncio.run(provider.generate_audio_clone(model, {
                    "text": "hi", "voice_name": "v", "sample_audio_url": "/static/ref.mp3",
                }))
        self.assertEqual(ctx.exception.code, "voice_clone_failed")
        self.assertIn("声音克隆上传失败", ctx.exception.message_zh)

    def test_online_tts_without_sample_unchanged(self) -> None:
        """无 sample_audio_url 时保持纯 TTS 行为:只有一次 /v1/audio/speech,voice 默认 alloy。"""
        provider = OnlineProvider()
        model = SimpleNamespace(model_code="FunAudioLLM/CosyVoice2-0.5B", model_type="audio")
        stub = _StubAsyncClient(lambda url, body: _fake_resp(text="audio", content=b"MP3"))
        settings = get_settings()
        with mock.patch("app.core.http_client.get_http_client", return_value=stub), \
                mock.patch.object(settings, "siliconflow_api_key", "test-siliconflow-key"):
            result = asyncio.run(provider.generate_audio_clone(model, {"text": "纯合成"}))
        self.assertEqual(len(stub.calls), 1)
        url, body = stub.calls[0]
        self.assertTrue(url.endswith("/v1/audio/speech"))
        self.assertEqual(body["voice"], "alloy")
        self.assertTrue(result["audio_url"].startswith("/static/"))


if __name__ == "__main__":
    unittest.main()
