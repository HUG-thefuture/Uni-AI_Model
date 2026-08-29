# backend（成员2/4：FastAPI 后端）

```text
backend/
├── app/
│   ├── core/       # 配置、安全、依赖（config / security / deps）
│   ├── models/     # SQLAlchemy 模型
│   ├── schemas/    # Pydantic 请求/响应
│   ├── routers/    # auth/user/admin/models/tasks/wallet/order/api_key/stats
│   ├── services/   # 业务逻辑（扣费事务、统计等）
│   └── providers/  # ModelProvider 适配层
├── tests/          # 接口测试
├── requirements.txt
└── .env.example    # 环境变量模板
```

统一规范：接口前缀 `/api`；返回 `{code, message, data, request_id}`；管理接口 `require_admin`。

## 成员2 WP01 交付（8/29）：数据模型与适配层骨架

- **ORM**（`app/models/`）：`models` / `ai_tasks` / `ai_call_logs` 三表；`user_id` 均按 `users.id` 逻辑外键关联（不建物理外键，应用层校验归属），与 `docs/数据字典.md` 口径一致。
- **适配层**（`app/providers/`）：`BaseProvider` 抽象（流式文本/图像/声音克隆/语音识别/视频/探活，全 async）；`OnlineProvider`（硅基流动 OpenAI 兼容，generate_text 流式+非流式已通）；`LocalProvider`（Ollama 骨架）；`MockProvider`（完整实现，无 Key 演示兜底）；`factory.get_provider()` 按 vendor 单例分发。
- **调用日志**（`app/services/call_log.py`）：每次 Provider 调用统一落库 `ai_call_logs`（request_id/耗时/结果/错误码）。
- **可运行骨架**（`app/main.py`）：request_id 中间件（`X-Request-Id` 响应头贯穿）、统一返回与异常处理、`GET /api/health` 探针。
- **密钥环境变量方案**：见 `.env.example`。`DATABASE_URL`/`SECRET_KEY` 缺失启动即失败；`SILICONFLOW_API_KEY` 只存环境变量、绝不入库绝不进 git，未配置时线上调用报中文错误、可用 Mock 全链路演示。

### 快速启动

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env      # 填好 DATABASE_URL / SECRET_KEY
python -m app.init_db       # 建成员2的三张表(MySQL) —— 全量建表见 sql/
uvicorn app.main:app --reload --port 8000
# 探针: curl http://127.0.0.1:8000/api/health
```

### 测试

```bash
python -m pytest tests -q   # 12 个用例:三表建表/约束、Mock 流式、工厂、配置缺项报错、统一返回
```

### 真实 Key 验证(D1 硬门槛)

```bash
$env:SILICONFLOW_API_KEY="sk-xxxx"; python ../scripts/verify_siliconflow.py
```

