"""演示数据 seed(WP09):本地演示/评审用,幂等可重复执行。

用法(在 backend/ 目录下执行;sqlite 演示库示例):

    DATABASE_URL=sqlite:///./demo.db SECRET_KEY=demo python scripts/seed_demo.py
    # MySQL 演示库:DATABASE_URL=mysql+pymysql://... SECRET_KEY=... python scripts/seed_demo.py

内容:
- 2 个演示用户 demo_user / demo_admin(密码哈希用 app.core.security.hash_password,
  成员1 用户模块就绪后由注册流程创建,本脚本仅保证演示链路可登录态展示);
- 钱包(余额 1000 分);
- 全部模板模型(基础 + 阿里百炼 DashScope 等,复用 scripts/seed_models.py 的
  模板 upsert 逻辑,幂等);
- 每个模型至少 1 条 succeeded 的 ai_tasks:
  文本模型附 chat_sessions / chat_messages;图像/音频/视频模型 result_url
  使用 /static/ 样例路径;每个模型另写 ai_call_logs 成功记录若干;
- 幂等:用户按 username 判重、模型按 model_code+provider_type upsert、
  任务/会话/日志按固定 request_id 判重,重复执行不重复插入。
"""
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal, init_db  # noqa: E402
from app.models.ai_call_log import AiCallLog  # noqa: E402
from app.models.ai_task import AiTask  # noqa: E402
from app.models.model import Model  # noqa: E402
from app.models.support import ChatMessage, ChatSession, User, Wallet  # noqa: E402

DEMO_PASSWORD = "demo123456"
DEMO_BALANCE = 1000
LATENCY_DEMO_MS = 1200  # 演示用固定耗时

# /static/ 样例路径(演示展示用;真实文件可后续放入 uploads/samples/)
SAMPLE_IMAGE_URLS = ["/static/samples/demo-image-1.png", "/static/samples/demo-image-2.png"]
SAMPLE_AUDIO_URL = "/static/samples/demo-audio.mp3"
SAMPLE_VIDEO_URL = "/static/samples/demo-video.mp4"

DEMO_USERS = (
    ("demo_user", "user", "演示普通用户"),
    ("demo_admin", "admin", "演示管理员"),
)

DEMO_PROMPTS = {
    "text": "用一句话介绍四川高校 AI 大模型门户",
    "image": "四川高校校园晚霞,国潮插画风",
    "audio": "将这段校园广播稿克隆为标准普通话音色",
    "video": "三分钟介绍四川高校 AI 大模型门户的宣传短片文案",
}


def _demo_password_hash() -> str:
    """演示用户密码哈希:使用正式算法 app.core.security.hash_password,
    保证与 /api/auth/login 的校验逻辑一致。"""
    from app.core.security import hash_password
    return hash_password(DEMO_PASSWORD)


def _task_request_id(model_code: str, provider_type: str, seq: int) -> str:
    return f"demo-seed-{provider_type}-{model_code.replace('/', '_').replace(':', '_')}-{seq:02d}"


def ensure_users(db) -> dict:
    """按 username 判重创建演示用户与钱包(余额 1000,已存在不动)。"""
    users = {}
    for username, role, _desc in DEMO_USERS:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user is None:
            user = User(username=username, password_hash=_demo_password_hash(),
                        role=role, status=1)
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[seed] 新增用户: {username}({role})")
        else:
            print(f"[seed] 用户已存在: {username}({user.role})")
        wallet = db.get(Wallet, user.id)
        if wallet is None:
            db.add(Wallet(user_id=user.id, balance=DEMO_BALANCE))
            db.commit()
            print(f"[seed] 新增钱包: {username} 余额 {DEMO_BALANCE} 分")
        users[username] = user
    return users


def load_models(db) -> list[Model]:
    """复用 scripts/seed_models.py 的模板 upsert 逻辑写入全部模板模型(幂等)。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import seed_models  # noqa: PLC0415 同目录模块,运行时导入

    items = seed_models.load_template()
    seed_models.upsert_models(db, items)
    return db.query(Model).filter(Model.status == "enabled").all()


def _text_task(db, user_id: int, model: Model) -> bool:
    """文本模型:succeeded 任务 + 会话(user+assistant 消息)+ 调用日志。幂等按 request_id。"""
    request_id = _task_request_id(model.model_code, model.provider_type, 1)
    if db.query(AiTask).filter(AiTask.request_id == request_id).one_or_none():
        print(f"[skip] 任务已存在: {request_id}")
        return False
    prompt = DEMO_PROMPTS["text"]
    reply = (f"【演示回复】四川高校 AI 大模型门户是面向全省高校的统一大模型服务平台,"
             f"当前演示数据由 seed_demo.py 生成(模型 {model.name})。")
    task = AiTask(
        request_id=request_id, user_id=user_id, model_id=model.id, task_type="text",
        prompt=prompt, status="succeeded", result_text=reply,
        cost=model.price_per_call or 0, cost_status="settled", latency_ms=LATENCY_DEMO_MS,
    )
    db.add(task)
    session = ChatSession(user_id=user_id, title=prompt[:20], model_id=model.id)
    db.add(session)
    db.flush()
    db.add_all([
        ChatMessage(session_id=session.id, role="user", content=prompt, model_id=model.id),
        ChatMessage(session_id=session.id, role="assistant", content=reply,
                    model_id=model.id, tokens_used=max(1, (len(prompt) + len(reply)) // 2)),
    ])
    db.add(AiCallLog(request_id=request_id, user_id=user_id, model_id=model.id,
                     provider=model.vendor, latency_ms=LATENCY_DEMO_MS,
                     success=True, error_code=None))
    print(f"[seed] 文本任务+会话: {model.name}({request_id})")
    return True


def _media_task(db, user_id: int, model: Model) -> bool:
    """图像/音频/视频模型:succeeded 任务(result_url=/static/ 样例)+ 调用日志。"""
    mtype = model.model_type
    request_id = _task_request_id(model.model_code, model.provider_type, 1)
    if db.query(AiTask).filter(AiTask.request_id == request_id).one_or_none():
        print(f"[skip] 任务已存在: {request_id}")
        return False
    if mtype == "image":
        result_url = json.dumps(SAMPLE_IMAGE_URLS, ensure_ascii=False)
    elif mtype == "audio":
        result_url = SAMPLE_AUDIO_URL
    elif mtype == "video":
        result_url = SAMPLE_VIDEO_URL
    else:  # 未知类型兜底:按文本处理
        return _text_task(db, user_id, model)
    task = AiTask(
        request_id=request_id, user_id=user_id, model_id=model.id, task_type=mtype,
        prompt=DEMO_PROMPTS.get(mtype, DEMO_PROMPTS["text"]), status="succeeded",
        result_url=result_url, cost=model.price_per_call or 0, cost_status="settled",
        latency_ms=LATENCY_DEMO_MS,
    )
    db.add(task)
    db.add(AiCallLog(request_id=request_id, user_id=user_id, model_id=model.id,
                     provider=model.vendor, latency_ms=LATENCY_DEMO_MS,
                     success=True, error_code=None))
    print(f"[seed] {mtype} 任务: {model.name}({request_id})")
    return True


def _extra_call_logs(db, user_id: int, model: Model, count: int = 2) -> int:
    """每个模型补几条 ai_call_logs 成功记录(固定 request_id 判重)。"""
    added = 0
    for seq in range(2, 2 + count):
        request_id = _task_request_id(model.model_code, model.provider_type, seq)
        if db.query(AiCallLog).filter(AiCallLog.request_id == request_id).one_or_none():
            continue
        db.add(AiCallLog(request_id=request_id, user_id=user_id, model_id=model.id,
                         provider=model.vendor, latency_ms=LATENCY_DEMO_MS + seq * 100,
                         success=True, error_code=None))
        added += 1
    return added


def main() -> int:
    try:
        init_db()  # 幂等建表
    except Exception as exc:  # noqa: BLE001
        print(f"[seed] 初始化失败: {exc}", file=sys.stderr)
        print("[seed] 请确认已设置 DATABASE_URL / SECRET_KEY 环境变量", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        users = ensure_users(db)
        models = load_models(db)
        demo_user = users["demo_user"]

        created_tasks = 0
        for model in models:
            if model.model_type == "text":
                created_tasks += int(_text_task(db, demo_user.id, model))
            else:
                created_tasks += int(_media_task(db, demo_user.id, model))
            created_logs = _extra_call_logs(db, demo_user.id, model)
            if created_logs:
                print(f"[seed] 调用日志 {created_logs} 条: {model.name}")

        db.commit()

        # 钱包对平:演示任务全部 succeeded(settled),total_consumed 与任务代价一致
        # (演示库余额固定 1000 分,视为已充值,不随演示任务变动)
        if created_tasks:
            settled_sum = (
                db.query(AiTask)
                .filter(AiTask.user_id == demo_user.id, AiTask.cost_status == "settled")
                .with_entities(AiTask.cost)
                .all()
            )
            wallet = db.get(Wallet, demo_user.id)
            wallet.total_consumed = sum(c[0] or 0 for c in settled_sum)
            db.commit()

        # 汇总输出
        total_tasks = db.query(AiTask).filter(AiTask.user_id == demo_user.id).count()
        total_logs = db.query(AiCallLog).filter(AiCallLog.user_id == demo_user.id).count()
        total_sessions = db.query(ChatSession).filter(
            ChatSession.user_id == demo_user.id).count()
        wallet = db.get(Wallet, demo_user.id)
        print("-" * 60)
        print(f"[seed] 完成: 用户 {len(users)} 个, 模型 {len(models)} 个, "
              f"本次新增任务 {created_tasks} 个")
        print(f"[seed] 演示用户 demo_user 现有: 任务 {total_tasks}, 会话 {total_sessions}, "
              f"调用日志 {total_logs}, 钱包余额 {wallet.balance} 分")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
