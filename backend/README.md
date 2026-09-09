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
python -m app.init_db       # 一步初始化:建表 + 写入全部模型种子(含阿里百炼,幂等)
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

# 3. 重建种子模型(推荐 python -m app.init_db 一步建表+全量种子;或单模板补种如下)
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
  任务失败不扣费(冻结金额全额退回);
- 管理端详情 `GET /api/admin/models/{id}` 不受影响,可查看近 7 天逐日调用量
  (daily_stats)与错误分布(error_stats)排障。

### 本地自测(不依赖真实 Ollama)

```bash
.venv/Scripts/python -m pytest tests/test_local_model.py -q
# 用 httpx.MockTransport 模拟 Ollama SSE/JSON 响应,覆盖流式/非流式/探活/缓存/联动
```

## 性能与稳定性参数(WP09 固化,D6 后冻结)

> 以下参数自 WP09 起固化,**D6 之后冻结**,调整需走全组评审并同步 `.env.example`。

### 连接池(`app/core/db.py`,MySQL 分支)

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `pool_size` | 20 | 常驻连接数 |
| `max_overflow` | 10 | 突发溢出连接上限(峰值 30) |
| `pool_recycle` | 1800 | 空闲连接 30 分钟回收,避免 MySQL wait_timeout 断连 |
| `pool_pre_ping` | True | 每次取连接前探活 |

sqlite 分支(测试/演示)不套用上述池参数,保持 `check_same_thread=False`。

### 慢查询日志

`app/core/db.py` 经 SQLAlchemy `before/after_cursor_execute` 事件记录单条 SQL 耗时,
超过 `SLOW_QUERY_MS`(默认 **500ms**)记 warning 日志(logger `app.db`)。

### 超时 / 重试 / 限流(来自 `.env.example`)

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `PROVIDER_CONNECT_TIMEOUT` | 10s | 上游连接超时 |
| `PROVIDER_READ_TIMEOUT_TEXT / IMAGE / AV` | 60 / 120 / 300s | 按任务类型读取超时 |
| `PROVIDER_MAX_RETRIES` | 2 | 仅幂等请求,指数退避 1s/2s |
| `SSE_FIRST_BYTE_TIMEOUT` | 15s | 流式首字节超时 |
| `SSE_TOTAL_TIMEOUT` | 120s | 单次流式总时长上限 |
| `OPENAPI_RATE_LIMIT_PER_MIN` | 30 | 单 API Key 每分钟调用上限 |
| `VIDEO_POLL_INTERVAL_SEC / MAX_SEC` | 5 / 300 | 视频句柄轮询间隔/上限 |
| `JWT_EXPIRE_HOURS` | 24 | 登录态有效期 |
| `CORS_ORIGINS` | `""` | 逗号分隔 CORS 白名单;为空仅允许 localhost/127.0.0.1,生产必须显式配置 |

### 短信验证(阿里云 Dysmsapi)

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `ALIYUN_SMS_ACCESS_KEY_ID/SECRET` | `""` | 阿里云 AccessKey(建议 RAM 子账号,仅授权短信权限);4 项短信配置齐全才真实发信 |
| `ALIYUN_SMS_SIGN_NAME` / `ALIYUN_SMS_TEMPLATE_CODE` | `""` | 短信签名/模板 CODE(变量为 `${code}`) |
| `SMS_DEBUG` | `false` | 未配置阿里云时回显验证码到响应(仅开发/演示环境开启!) |
| `SMS_CODE_EXPIRE_SEC` / `SMS_CODE_MAX_ATTEMPTS` | 300 / 5 | 验证码有效期/最大错误次数 |
| `SMS_SEND_PER_DAY` / `SMS_IP_SEND_PER_DAY` | 10 / 20 | 同号每日/同 IP 每日发送上限 |

**免费额度申请步骤**(个人/企业认证后):控制台开通短信服务 → 国内消息「测试签名/模板」申请(免费,测试签名【阿里云短信测试】+ 对应测试模板,仅可发给控制台绑定的白名单手机号)→ 把签名/模板 CODE 填入 `.env` → 新用户默认含免费条数。正式签名/模板需审核,用于非白名单手机号。

### 支付(支付宝沙箱 + 内置模拟收银台)

- **未配置** `ALIPAY_APP_ID/ALIPAY_PRIVATE_KEY/ALIPAY_PUBLIC_KEY` 时自动使用**内置模拟收银台**:充值下单 → `/pay.html` 页面「确认支付(沙箱模拟)」→ mock-pay 幂等入账,零配置演示完整闭环;
- **配置后**走支付宝沙箱真实网关(默认 `https://openapi-sandbox.dl.alipaydev.com/gateway.do`):开放平台沙箱 APPID → 沙箱密钥工具生成 RSA2 密钥对 → 应用私钥填 `ALIPAY_PRIVATE_KEY`、**支付宝公钥**填 `ALIPAY_PUBLIC_KEY`(注意不是应用公钥)→ 下单跳转沙箱收银台,用沙箱买家账号支付;`ALIPAY_RETURN_URL` 填 `http://127.0.0.1:4174/pay.html` 即可本地闭环(回跳后同步查单);公网部署再配 `ALIPAY_NOTIFY_URL` 接收异步通知;
- 金额口径(2026-09-07 起):全平台按「元」记账,账本内部为微元(1 元 = 1_000_000 微元);存量积分数据用 `scripts/migrate_ledger_to_yuan.py` 一次性迁移;生产上线把 `ALIPAY_GATEWAY` 换成正式网关。

### 开放平台接入信息(便于复制)

创建/管理 API Key 时,门户「开放平台」页同步展示可直接复制的接入信息:
API Base URL(`{后端地址}/api/v1`)、对话接口路径、可用模型的 `vendor / model_code` 列表,
以及自动填入新 Key 的 curl / Python 调用示例(Key 明文仅在创建响应返回一次)。

### 运营参数

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DEFAULT_REGISTER_POINTS` | 10 | 新用户注册赠送金额(元,零门槛体验模型) |
| `TOKEN_MARKUP_PCT` | 130 | 盈利:按 token 模型售价 = 供应商成本价 × 加价比例(130=加价30%);模型行 `token_markup_pct` 非空时优先 |

管理端「概览」提供按 token 模型的盈利报表(收入/供应商成本/毛利);用户「用量统计」页可查看最近 20 次调用的逐条 token 用量与扣费,个人账单的消费流水同样带模型名与 token 明细,支持 CSV 导出。

### HTTP 连接复用(WP09 就绪,WP10 已接入)

`app/core/http_client.py` 提供进程级共享 `httpx.AsyncClient` 单例
(`max_connections=100 / max_keepalive_connections=20`)。providers 层
(`providers/base.py` 的非流式 POST 与流式建连、DashScope 任务轮询/下载)已全部
接入该单例;短信发送与支付宝查单同样复用。

### Mock 显式延迟(测试/演示用)

`MockProvider` 支持 `mock_delay_sec` 覆盖默认 2-5s 随机延迟,优先级:
`params["mock_delay_sec"]` > `models.config_json` > 全局 `MOCK_DELAY_SEC`。
用于超时链路演练(如 `mock_delay_sec=5` + `SSE_TOTAL_TIMEOUT=2` 验证「生成超时不扣费」)。

### 稳定性测试与演示数据

```bash
.venv/Scripts/python scripts/test_m_series.py   # M-01~M-08 稳定性用例,结果写 docs/m-series-result.md
DATABASE_URL=sqlite:///./demo.db SECRET_KEY=demo .venv/Scripts/python scripts/seed_demo.py
# 演示数据(2 用户/4 模型/任务/会话/调用日志),幂等可重复执行
```

## 环境要求(WP10 补全)

| 组件 | 版本要求 | 说明 |
| --- | --- | --- |
| Python | **3.11.9**(3.11+) | 仓库根 `.python-version` 已锁定;pyenv/uv 自动识别 |
| MySQL | **8.0** | 生产/联调库;本地演示可用 sqlite(见 seed_demo 示例) |
| Ollama | 可选 | 本地模型(qwen2.5)演示用;不装则 local 模型 available=false,其余功能不受影响 |

## .env 变量说明(对照 .env.example,全部变量)

| 变量 | 必填 | 默认 | 用途 |
| --- | --- | --- | --- |
| `DATABASE_URL` | **是** | — | 数据库连接串,缺失启动即失败。MySQL 示例:`mysql+pymysql://root:password@127.0.0.1:3306/ai_portal?charset=utf8mb4`;sqlite 示例:`sqlite:///./demo.db` |
| `SECRET_KEY` | **是** | — | JWT 签名密钥,缺失启动即失败;生产必须更换,禁止提交真实值 |
| `SILICONFLOW_API_KEY` | 否 | `""` | 硅基流动 API Key(https://cloud.siliconflow.cn);只存环境变量,绝不入库绝不进 git;为空时线上模型调用报中文错误,可用 Mock 全链路联调 |
| `OLLAMA_BASE_URL` | 否 | `http://localhost:11434` | Ollama 本地服务地址;models.endpoint 未配置时也作为调用端点回退 |
| `PROVIDER_CONNECT_TIMEOUT` | 否 | `10` | 上游连接超时(秒) |
| `PROVIDER_READ_TIMEOUT_TEXT` | 否 | `60` | 文本任务读取超时(秒) |
| `PROVIDER_READ_TIMEOUT_IMAGE` | 否 | `120` | 图像任务读取超时(秒) |
| `PROVIDER_READ_TIMEOUT_AV` | 否 | `300` | 音频/视频任务读取超时(秒) |
| `PROVIDER_MAX_RETRIES` | 否 | `2` | 失败重试次数(仅幂等请求,指数退避 1s/2s) |
| `API_PREFIX` | 否 | `/api` | 接口前缀(全组冻结为 /api);另自动挂 /api/v1 兼容别名 |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 DEBUG/INFO/WARNING |
| `JWT_EXPIRE_HOURS` | 否 | `24` | JWT 有效期(小时,全组冻结 24h) |
| `SSE_FIRST_BYTE_TIMEOUT` | 否 | `15` | 流式上游首字节超时(秒) |
| `SSE_TOTAL_TIMEOUT` | 否 | `120` | 单次流式总时长上限(秒) |
| `UPLOAD_DIR` | 否 | `uploads` | 上传文件落盘目录(相对 backend/ 或绝对路径),经 /static 访问 |
| `OPENAPI_RATE_LIMIT_PER_MIN` | 否 | `30` | 单 API Key 每分钟调用上限(开放平台) |
| `VIDEO_POLL_INTERVAL_SEC` | 否 | `5` | 视频句柄轮询间隔(秒) |
| `VIDEO_POLL_MAX_SEC` | 否 | `300` | 视频轮询总上限(秒),超时判 failed 不扣费 |
| `SLOW_QUERY_MS` | 否 | `500` | 慢查询日志阈值(毫秒),超过记 warning(logger `app.db`);在 config.py 中定义,未列入 .env.example 也可直接设环境变量覆盖 |
| `MOCK_DELAY_SEC` | 否 | `None` | Mock 全局显式延迟(秒,测试/演示用);None=2-5s 随机 |

`DATABASE_URL` / `SECRET_KEY` 为必填,缺失时启动即失败并明确提示缺哪个变量。

## 本地启动步骤(全新环境)

```bash
cd backend

# 1. 创建虚拟环境(建议 3.11.9)
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1 / Git Bash: source .venv/Scripts/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 准备 .env
copy .env.example .env        # Linux/macOS: cp .env.example .env
# 编辑 .env:必填 DATABASE_URL / SECRET_KEY;联调线上模型填 SILICONFLOW_API_KEY

# 4. 一步初始化:幂等建表 + 写入全部 9 个模型种子(硅基流动/Ollama/阿里百炼,可重复执行)
python -m app.init_db

# 5. (可选)单模板补种:python scripts/seed_models.py / python scripts/seed_dashscope_models.py

# 6. (可选)写入演示数据:2 个演示用户 + 任务/会话/调用日志,断网演示可用
DATABASE_URL=sqlite:///./demo.db SECRET_KEY=demo python scripts/seed_demo.py

# 7. 启动
uvicorn app.main:app --reload --port 8000
# 探针: curl http://127.0.0.1:8000/api/health
# 接口文档: http://127.0.0.1:8000/api/docs (Swagger UI)
```

## 初始化命令一览

| 命令 | 作用 |
| --- | --- |
| `python -m app.init_db` | **一步初始化(推荐)**:幂等建表 + 合并写入 docs/ 下全部 `model-config-*.json`(9 个模型,含阿里百炼);git pull 最新模型数据后执行这一条即可 |
| `python -m app.init_db --schema-only` | 仅幂等建表并增量对齐结构,不写模型种子 |
| `python -m app.schema_sync --check` | 只检查 ORM 与数据库的缺表/缺列/缺索引,不修改数据 |
| `python -m app.schema_sync --apply` | 按 ORM 增量修复已有库的缺表/缺列/缺索引,不删除字段或数据 |
| `python scripts/seed_models.py` | 单模板补种:仅 `docs/model-config-template.json` 的 4 个模型 |
| `python scripts/seed_dashscope_models.py` | 单模板补种:仅 `docs/model-config-dashscope.json` 的 5 个阿里百炼模型 |
| `python scripts/seed_demo.py` | 演示数据(demo_user/demo_admin、钱包余额 1000、任务/会话/日志),幂等可重复执行 |
| `python scripts/test_m_series.py` | M-01~M-08 稳定性用例,结果写 `docs/m-series-result.md` |

管理员账号由成员1 提供(`POST /api/auth/register` 注册后置 role=admin,或用 seed_demo 的 demo_admin);模型管理接口 `/api/admin/models` 全部需要管理员 JWT。

## 常见问题

### 1. Ollama 未启动

- 现象:门户 `GET /api/models` 中本地模型 `available=false`(探活 2s 超时,结果缓存 60s,期间不重试);发起对话返回错误「本地模型服务未启动,请联系管理员」(error_code=provider_unreachable),任务失败不扣费。
- 处理:启动 Ollama(`ollama serve` / 桌面端启动),确认 `ollama list` 有对应模型;`GET /api/admin/models/{id}` 的 error_stats 可看到 provider_unreachable 计数。缓存过期(≤60s)后 available 自动恢复 true。

### 2. API Key 无效(401 排查项)

`POST /api/chat/completions` 返回 401「API Key 无效或已禁用」时依次检查:

1. 请求头是否为 `Authorization: Bearer sk-xxx`(Bearer 后有一个空格;Key 以 sk- 开头);
2. Key 是否抄错(库内只存 sha256 哈希,明文丢失无法找回,只能重新生成);
3. api_keys.status 是否为 enabled(禁用立即生效);
4. Key 是否过期(expires_at < 当前时间);
5. Key 所属 users.status 是否为 1(用户被禁用时 Key 一并失效)。

### 3. SSE 被 Nginx 缓冲(流式输出变成"一次性吐出")

- 后端响应已带 `X-Accel-Buffering: no`(业务 SSE 与开放平台流式均带),Nginx 应遵守该头;
- 若仍被缓冲,在 Nginx 对应 location 显式加:`proxy_buffering off;`(并确认未开 gzip 对 text/event-stream);
- 客户端测试时用 `curl -N` 关闭本地缓冲。

### 4. 慢查询日志在哪看

- `app/core/db.py` 经 SQLAlchemy 事件统计单条 SQL 耗时,超过 `SLOW_QUERY_MS`(默认 500ms)以 **warning** 级别输出,logger 名为 **`app.db`**;
- 后台用 uvicorn 直跑时直接看 stdout(uvicorn 默认日志与 SQL 慢日志混排,含时间戳与 SQL 语句);按 `LOG_LEVEL=INFO` 起即可看到 warning;
- 生产若日志进了文件,`grep "app.db"` 或按 warning 级别过滤即可定位慢 SQL。

