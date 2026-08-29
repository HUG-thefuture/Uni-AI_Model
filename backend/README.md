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

## 统一环境约定（全组执行）

- Python 版本：**3.11.9**（仓库根目录已放 `.python-version`，pyenv/uv 会自动识别）
- 每个成员本地必须用虚拟环境：`python -m venv .venv`，依赖全部装在虚拟环境里
- 安装依赖：`pip install -r requirements.txt`
- 联调前如出现"本地能跑、别人报错"，先对比 `python --version` 是否为 3.11.9

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

## 本地模型演示环境(WP08)

本地模型走 Ollama 的 OpenAI 兼容通路(`POST {OLLAMA_BASE_URL}/v1/chat/completions`,
流式 SSE + 非流式),探活走 `GET {OLLAMA_BASE_URL}/api/tags`,无需任何密钥。

### 搭建步骤

```bash
# 1. 安装并拉取本地模型(Ollama 官网下载安装后)
ollama pull qwen2.5:1.5b
ollama list                    # 确认模型就绪(建议顺带 qwen2.5:3b)

# 2. 配置 OLLAMA_BASE_URL(backend/.env,默认 http://localhost:11434,可省略)
echo OLLAMA_BASE_URL=http://localhost:11434 >> .env

# 3. 重建 4 个种子模型(幂等:线上对话/线上文生图 + 本地 qwen2.5:3b / qwen2.5:1.5b)
python scripts/seed_models.py

# 4. 启动后端,打开前端模型广场
uvicorn app.main:app --reload --port 8000
```

### 前端表现(在线/离线标签)

- `GET /api/models` 每个模型新增 `available` 字段:local 模型实时轻量探活 Ollama
  `/api/tags`(2 秒超时,结果模块级缓存 60 秒),前端据此渲染「在线/离线」标签;
  online/mock 模型恒为 `true`(不做真实探活,避免拖慢列表);
- 本地模型在线时:对话走流式增量,体验与线上模型一致;本地模型不支持的
  图像/声音/视频任务统一返回「该模型不支持该任务类型」(provider_not_supported)。

### 停掉 Ollama 进程后的表现(断网兜底演练)

- 门户列表:本地模型 `available=false`(60 秒缓存过期后自动恢复探测),列表照常返回不阻塞;
- 发起调用:返回「本地模型服务未启动,请联系管理员」(provider_unreachable),
  任务失败不扣费(冻结积分全额退回);
- 管理端详情 `GET /api/admin/models/{id}` 不受影响,可查看近 7 天逐日调用量
  (daily_stats)与错误分布(error_stats)排障。

### 本地自测(不依赖真实 Ollama)

```bash
.venv/Scripts/python -m pytest tests/test_local_model.py -q
# 用 httpx.MockTransport 模拟 Ollama SSE/JSON 响应,覆盖流式/非流式/探活/缓存/联动
```

