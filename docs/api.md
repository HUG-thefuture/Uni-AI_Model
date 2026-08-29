# 四川高校 AI 大模型门户 · 后端接口文档(成员2 · WP10 终版)

版本 v1.0 ｜ 日期 2026-08-29 ｜ 维护人:成员2(模型与 AI 任务)

> 本文档与代码逐接口核对(以 `app.openapi()` 与 `backend/app/routers/` 实现为准),所有示例 JSON 均由代码推导,可直接 curl 复现。Base URL 统一按本地启动 `http://127.0.0.1:8000` 书写。

---

## 0. 概览

### 0.1 统一返回结构(全组冻结)

所有业务接口(除 `POST /api/chat/completions` 返回 OpenAI 兼容结构外)统一返回:

```json
// 成功(「示例」)
{
  "code": 0,
  "message": "success",
  "data": { },
  "request_id": "3f2a9c8e-1c4b-4f6e-9a2d-7b8c1d2e3f4a"
}
```

```json
// 失败(「示例」,HTTP 状态码同步为对应错误码)
{
  "code": 40900,
  "message": "积分不足,请先充值",
  "data": null,
  "request_id": "3f2a9c8e-1c4b-4f6e-9a2d-7b8c1d2e3f4a"
}
```

- 失败时 `code` 默认为 `HTTP状态码 × 100`(如 404 → `40400`);个别业务异常可自定义 code。
- 参数校验失败(Pydantic)返回 400,message 形如 `"参数错误: body.model_id Input should be a valid integer"`。

### 0.2 错误码列表(全组冻结)

| HTTP | code(默认) | message(典型) | 触发场景 |
| --- | --- | --- | --- |
| 400 | 40000 | 参数错误:… / 不支持的文件类型 / 音频时长超过模型上限 | 参数校验失败、枚举非法、上传校验不过 |
| 401 | 40100 | 未登录或凭证失效 / 缺少API Key / API Key 无效或已禁用 | JWT 或 API Key 鉴权失败 |
| 403 | 40300 | 无权限,需要管理员身份 / 无权限访问该会话 / 无权限查看该任务 / 无权限操作该任务 | 权限不足或访问他人资源 |
| 404 | 40400 | 模型不存在 / 会话不存在 / 任务不存在 | 资源不存在 |
| 409 | 40900 | 模型已存在 / 模型维护中,暂不可调用 / 积分不足,请先充值 / 请勿重复提交 / 该模型存在 N 个进行中的任务,禁止删除 / 仅失败任务可以重试 | 唯一冲突、状态冲突、幂等冲突 |
| 429 | 42900 | 请求过于频繁,请稍后重试 | 开放平台单 Key 每分钟超 30 次 |
| 500 | 50000 | 服务异常 | 未捕获异常(响应同时记录服务端日志) |
| 502 | 50200 | 生成失败,本次不扣费 | 开放平台上游调用失败/超时(不扣费) |

### 0.3 分页规范

通用查询参数:`page`(默认 1,≥1)、`page_size`(默认 10,1..100)。返回:

```json
{ "total": 4, "page": 1, "page_size": 10, "items": [ ] }
```

### 0.4 双前缀说明

- `/api` 为全组冻结前缀,前后端一律使用 `/api/...`;
- `/api/v1` 为兼容别名(如 `/api/v1/models` 与 `/api/models` 完全等价),仅供 WP 提示词历史兼容,新代码不使用。

### 0.5 X-Request-Id 链路

- 每次请求生成 UUID4,写入响应头 `X-Request-Id`,贯穿统一返回体 `request_id` 与服务端日志;
- 客户端也可携带请求头 `X-Request-Id: <自定义值>`,服务端会沿用该值便于链路追踪。

### 0.6 鉴权方式一览

| 鉴权 | 头部 | 适用接口 |
| --- | --- | --- |
| JWT | `Authorization: Bearer <token>`(登录接口获取,24h 有效) | 模型广场、会话、任务、上传 |
| JWT + 管理员 | 同上,且要求 `role=admin` | `/api/admin/models` 全部 |
| API Key | `Authorization: Bearer sk-xxx` | `/api/chat/completions` 开放平台 |
| 无 | — | `GET /api/health` |

---

## 1. 健康检查

### GET /api/health

- 鉴权:无
- 请求参数:无

响应 200(「示例」):

```json
{
  "code": 0,
  "message": "success",
  "data": { "status": "up", "service": "ai-portal-backend" },
  "request_id": "9d2b3f..."
}
```

curl:

```bash
curl http://127.0.0.1:8000/api/health
```

错误码:无(服务不可达时为连接层错误)。

---

## 2. 模型广场(门户端)

### GET /api/models

- 鉴权:JWT(需登录)
- 仅返回 `status=enabled` 模型;**不暴露** `endpoint` 与 `config_json`
- `available`:local 模型轻量探活 Ollama `GET /api/tags`(2s 超时,结果缓存 60s);online/mock 恒为 `true`

查询参数:

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| category | string | 否 | 类别筛选:online / local(非法值 400) |
| type | string | 否 | 模型类型:text / image / audio / video(非法值 400) |
| keyword | string | 否 | 关键字,模糊匹配 name/description,≤100 字符 |
| page | int | 否 | 页码,默认 1 |
| page_size | int | 否 | 每页条数,默认 10,最大 100 |

响应 200(「示例」,data):

```json
{
  "total": 4,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "id": 1,
      "name": "Qwen2.5-7B 对话(线上)",
      "vendor": "siliconflow",
      "provider_type": "online",
      "model_type": "text",
      "description": "硅基流动托管的中英文对话模型,用于文本对话主链路",
      "capability_tags": ["对话", "推理"],
      "price_per_call": 1,
      "status": "enabled",
      "available": true
    }
  ]
}
```

curl:

```bash
TOKEN="登录返回的 JWT"
curl -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/api/models?category=online&type=text&page=1&page_size=10"
```

错误码:400(category/type 非法)、401(未登录)。

---

## 3. 管理端模型(全部需管理员 JWT)

### 3.1 GET /api/admin/models

模型管理列表:全量分页(**含 disabled**)。查询参数与模型广场一致(category / type / keyword / page / page_size)。

响应 200(「示例」,data.items 单项为管理端全量字段):

```json
{
  "id": 1,
  "name": "Qwen2.5-7B 对话(线上)",
  "model_code": "Qwen/Qwen2.5-7B-Instruct",
  "provider_type": "online",
  "model_type": "text",
  "vendor": "siliconflow",
  "endpoint": null,
  "price_per_call": 1,
  "max_duration_sec": null,
  "status": "enabled",
  "config_json": { "temperature": 0.7, "max_tokens": 1024 },
  "description": "硅基流动托管的中英文对话模型,用于文本对话主链路",
  "capability_tags": ["对话", "推理"],
  "created_at": "2026-08-29 10:00:00",
  "updated_at": "2026-08-29 10:00:00"
}
```

curl:

```bash
ADMIN_TOKEN="管理员登录返回的 JWT"
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://127.0.0.1:8000/api/admin/models?page=1&page_size=10"
```

错误码:401、403(非管理员)。

### 3.2 POST /api/admin/models

创建模型,成功 201。

请求体:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 | 展示名,1..100 |
| model_code | string | 是 | 厂商调用名,1..200 |
| provider_type | string | 是 | online / local(非法 400) |
| model_type | string | 是 | text / image / audio / video(非法 400) |
| vendor | string | 是 | siliconflow / ollama / mock(非法 400) |
| endpoint | string | 否 | 自定义端点,本地模型用,≤255 |
| price_per_call | int | 是 | 积分点/次,≥0 |
| max_duration_sec | int | 否 | 音视频时长上限(秒),≥0 |
| description | string | 否 | 模型说明,≤500 |
| capability_tags | string[] | 否 | 能力标签,如 ["对话"] |
| config_json | object/string | 否 | 非敏感参数(严禁存密钥),对象或 JSON 字符串 |

响应 201:data 同 3.1 单项结构(「示例」略,status 恒为 "enabled")。

curl:

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "Qwen2.5-7B 对话(线上)",
    "model_code": "Qwen/Qwen2.5-7B-Instruct",
    "provider_type": "online",
    "model_type": "text",
    "vendor": "siliconflow",
    "price_per_call": 1,
    "description": "对话主链路",
    "capability_tags": ["对话", "推理"],
    "config_json": {"temperature": 0.7, "max_tokens": 1024}
  }' \
  http://127.0.0.1:8000/api/admin/models
```

错误码:400(枚举非法/config_json 非法)、401、403、409(model_code+provider_type 冲突「模型已存在」)。

### 3.3 GET /api/admin/models/{id}

模型详情:3.1 全量字段 + 统计数据(WP08)。

响应 200(「示例」,data 追加字段):

```json
{
  "id": 1,
  "name": "Qwen2.5-7B 对话(线上)",
  "model_code": "Qwen/Qwen2.5-7B-Instruct",
  "provider_type": "online",
  "model_type": "text",
  "vendor": "siliconflow",
  "endpoint": null,
  "price_per_call": 1,
  "max_duration_sec": null,
  "status": "enabled",
  "config_json": { "temperature": 0.7, "max_tokens": 1024 },
  "description": "硅基流动托管的中英文对话模型",
  "capability_tags": ["对话", "推理"],
  "created_at": "2026-08-29 10:00:00",
  "updated_at": "2026-08-29 10:00:00",
  "call_stats_7d": { "total": 128, "success": 120, "success_rate": 0.9375 },
  "daily_stats": [
    { "date": "2026-08-23", "total": 12, "success": 12 },
    { "date": "2026-08-24", "total": 0, "success": 0 }
  ],
  "error_stats": [
    { "error_code": "provider_timeout", "count": 4 },
    { "error_code": "provider_auth", "count": 2 }
  ]
}
```

- `call_stats_7d`:近 7 天总调用/成功数/成功率(4 位小数);
- `daily_stats`:近 7 天逐日调用量,升序补 0;
- `error_stats`:近 7 天失败记录按 error_code 计数,前 10,倒序。

curl:

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://127.0.0.1:8000/api/admin/models/1
```

错误码:401、403、404(模型不存在)。

### 3.4 PUT /api/admin/models/{id}

部分更新:仅修改请求体中显式传入的字段(未传字段保持原值)。

请求体:同 3.2,但全部字段可选。

响应 200:data 同 3.1 单项结构。

curl:

```bash
curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"price_per_call": 2, "description": "更新后的说明"}' \
  http://127.0.0.1:8000/api/admin/models/1
```

错误码:400、401、403、404、409(改 model_code/provider_type 后与其他模型冲突)。

### 3.5 PUT /api/admin/models/{id}/status

启用/停用(幂等:状态一致直接返回)。

请求体:

```json
{ "status": "disabled" }
```

响应 200(「示例」):

```json
{
  "code": 0, "message": "success",
  "data": { "id": 1, "status": "disabled" },
  "request_id": "..."
}
```

停用后门户列表立即不可见;停用模型再发起任务返回 409「模型维护中,暂不可调用」。

curl:

```bash
curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"status": "disabled"}' \
  http://127.0.0.1:8000/api/admin/models/1/status
```

错误码:400(status 非法)、401、403、404。

### 3.6 DELETE /api/admin/models/{id}

物理删除。存在 `pending/processing` 任务引用则 409 拒绝。

响应 200(「示例」):`"data": { "id": 1 }`

curl:

```bash
curl -X DELETE -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://127.0.0.1:8000/api/admin/models/1
```

错误码:401、403、404、409(「该模型存在 N 个进行中的任务,禁止删除」)。

---

## 4. 会话

### 4.1 POST /api/chat/sessions

创建会话。校验模型存在且 enabled;标题先为「新会话」,首条消息后更新为输入前 20 字。

请求体:

```json
{ "model_id": 1 }
```

响应 200(「示例」,data):

```json
{
  "session_id": 1,
  "title": "新会话",
  "model_id": 1,
  "created_at": "2026-08-29T10:00:00"
}
```

curl:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model_id": 1}' \
  http://127.0.0.1:8000/api/chat/sessions
```

错误码:400(model_id 缺失/非法)、401、404(模型不存在)、409(模型维护中)。

### 4.2 GET /api/chat/sessions

我的会话分页,按 updated_at 倒序。

查询参数:`page`(默认 1)、`page_size`(默认 10,≤100)。

响应 200(「示例」,data):

```json
{
  "total": 1,
  "page": 1,
  "page_size": 10,
  "items": [
    {
      "session_id": 1,
      "title": "用一句话介绍四川高校 AI 大模型门",
      "model_id": 1,
      "created_at": "2026-08-29T10:00:00",
      "updated_at": "2026-08-29T10:01:00"
    }
  ]
}
```

curl:

```bash
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/chat/sessions?page=1&page_size=10"
```

错误码:401。

### 4.3 GET /api/chat/sessions/{session_id}/messages

历史消息按 created_at 正序;他人会话 403。

响应 200(「示例」,data):

```json
{
  "session_id": 1,
  "title": "用一句话介绍四川高校 AI 大模型门",
  "items": [
    { "id": 1, "role": "user", "content": "用一句话介绍四川高校AI大模型门户",
      "model_id": 1, "tokens_used": null, "created_at": "2026-08-29T10:00:30" },
    { "id": 2, "role": "assistant", "content": "四川高校AI大模型门户是……",
      "model_id": 1, "tokens_used": 128, "created_at": "2026-08-29T10:00:35" }
  ]
}
```

curl:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/chat/sessions/1/messages
```

错误码:401、403(他人会话)、404(会话不存在)。

---

## 5. AI 任务

### 5.0 异步任务通用说明(图像/声音/视频)

- 四态流转:`pending → processing → succeeded / failed`;
- 提交后立即返回 `{task_id, status:"pending"}`,后台执行,轮询 `GET /api/tasks/{id}` 查结果;
- 同一请求携带相同 `X-Request-Id` 头重复提交同一类任务 → 409「请勿重复提交」;
- 失败任务一律不扣费(冻结退回,cost=0、cost_status=refunded)。

### 5.1 POST /api/tasks/text(SSE 流式对话)

**响应为 `text/event-stream` 流式**,非统一 JSON 结构。

请求体:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| session_id | int | 是 | 会话 ID,需归属当前用户 |
| model_id | int | 是 | 模型 ID,需存在且 enabled 且 model_type=text(否则 409「该模型不支持文本对话」) |
| message | string | 是 | 用户输入,1..4000 字符 |

响应头:

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

(`X-Accel-Buffering: no` 显式禁用 Nginx 代理缓冲,部署时无需额外配置。)

SSE 事件帧(共三种,均为 `data: {json}\n\n` 格式):

```text
data: {"delta": "四川高校"}                                       ← 增量帧(逐段)
data: {"delta": "AI大模型门户是统一服务平台。"}                     ← 增量帧
data: {"done": true, "task_id": 1, "cost": 1}                     ← 结束帧(成功,已结算)
```

```text
data: {"error": {"code": "provider_timeout", "message": "生成超时,本次不扣费"}}   ← 结束帧(失败,已退费)
```

- 错误码 code 可能值:`provider_timeout`(超时)、`provider_unreachable`(本地模型未启动)、`provider_not_configured`(SILICONFLOW_API_KEY 未配置)、`internal_error`(其他异常);
- 超时:首字节 15s(`SSE_FIRST_BYTE_TIMEOUT`),总时长 120s(`SSE_TOTAL_TIMEOUT`);
- 客户端断连:按失败处理(不扣费),任务 failed;
- 成功后助手消息落库,可在 `GET /api/chat/sessions/{id}/messages` 查到完整历史。

curl(注意 `-N` 关闭客户端缓冲):

```bash
curl -N -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"session_id": 1, "model_id": 1, "message": "用一句话介绍四川高校AI大模型门户"}' \
  http://127.0.0.1:8000/api/tasks/text
```

错误码(建流前返回统一 JSON 结构):400(message 超长等)、401、404(模型/会话不存在)、403(他人会话)、409(模型维护中 / 非 text 模型 / 积分不足)。

### 5.2 POST /api/tasks/image

图像生成(异步四态)。

请求体:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| model_id | int | 是 | 需 model_type=image |
| prompt | string | 是 | 生成提示词,1..2000 |
| params.image_size | string | 否 | 尺寸,如 1024x1024,默认 1024x1024 |
| params.num | int | 否 | 生成数量 1..4,默认 1 |
| params.image_url | string | 否 | 图生图参考图 URL(预留) |

响应 200(「示例」,data):

```json
{ "task_id": 1, "status": "pending" }
```

curl:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model_id": 2, "prompt": "四川高校校园晚霞,国潮插画风", "params": {"image_size": "1024x1024", "num": 2}}' \
  http://127.0.0.1:8000/api/tasks/image
```

错误码:400、401、404(模型不存在)、409(模型维护中 / 非 image 模型 / 重复提交 / 积分不足)。

### 5.3 POST /api/tasks/audio/clone

声音克隆(异步四态)。

请求体:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| model_id | int | 是 | 需 model_type=audio |
| voice_name | string | 是 | 音色名,如 alloy,1..100 |
| text | string | 是 | 要合成的文本,1..5000 |
| sample_audio_url | string | 否 | 参考音频 URL(可来自 POST /api/uploads) |
| duration_sec | int | 否 | 参考音频时长(秒);超过模型 max_duration_sec 时 400 |

响应 200(「示例」,data):`{ "task_id": 2, "status": "pending" }`

curl:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model_id": 3, "voice_name": "alloy", "text": "将这段校园广播稿克隆为标准普通话音色"}' \
  http://127.0.0.1:8000/api/tasks/audio/clone
```

错误码:400(参数/时长超上限)、401、404、409(维护中 / 非 audio 模型 / 重复提交 / 积分不足)。

### 5.4 POST /api/tasks/audio/asr

语音识别(异步四态)。

请求体:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| model_id | int | 是 | 需 model_type=audio |
| audio_url | string | 是 | 音频 URL(可来自 POST /api/uploads 的 url),1..500 |
| duration_sec | int | 否 | 音频时长(秒),超模型上限 400 |

响应 200(「示例」,data):`{ "task_id": 3, "status": "pending" }`

成功后 `GET /api/tasks/{id}` 的 `result_text` 为转写文本。

curl:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model_id": 3, "audio_url": "/static/xxxx-clip.mp3"}' \
  http://127.0.0.1:8000/api/tasks/audio/asr
```

错误码:同 5.3。

### 5.5 POST /api/tasks/video

长文本转视频(异步四态,长耗时:后台提交上游并按 `VIDEO_POLL_INTERVAL_SEC=5` 轮询,上限 `VIDEO_POLL_MAX_SEC=300`)。

请求体:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| model_id | int | 是 | 需 model_type=video |
| text | string | 是 | 视频文案,1..2000 字(超长 400) |
| params.resolution | string | 否 | 分辨率,如 1280x720,≤20 字符 |
| params.duration_sec | int | 否 | 视频时长上限(秒),≥1 |

响应 200(「示例」,data):`{ "task_id": 4, "status": "pending" }`

curl:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"model_id": 4, "text": "三分钟介绍四川高校AI大模型门户的宣传短片文案", "params": {"resolution": "1280x720"}}' \
  http://127.0.0.1:8000/api/tasks/video
```

错误码:400(超长)、401、404、409(维护中 / 非 video 模型 / 重复提交 / 积分不足)。

> 说明:线上(硅基流动)视频接口上游未定,线上模型视频任务会以 502/failed「上游视频接口暂不可用,请使用 Mock 模型演示」收尾且不扣费;Mock 模型(vendor=mock)可演示完整 pending→processing→succeeded 链路。

### 5.6 GET /api/tasks

我的任务分页,按 id 倒序。

查询参数:

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| page / page_size | int | 否 | 同通用分页 |
| task_type | string | 否 | text / image / audio_clone / asr / video |

响应 200(「示例」,data.items 单项):

```json
{
  "id": 2,
  "task_type": "image",
  "status": "succeeded",
  "prompt": "四川高校校园晚霞,国潮插画风",
  "result_text": null,
  "result_url": "[\"https://dummyimage.com/1024x1024/4f7cff/ffffff.png&text=Mock+Image\"]",
  "error_message": null,
  "cost": 10,
  "latency_ms": 3210,
  "created_at": "2026-08-29T10:05:00"
}
```

- `result_url`:图像任务为 JSON 数组字符串(多图);音频克隆/视频为单个 URL 字符串;
- `processing` 状态的任务额外附 `elapsed_sec`(距创建秒数);
- 文本任务 `result_text` 为完整回复,语音识别 `result_text` 为转写文本。

curl:

```bash
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8000/api/tasks?page=1&page_size=10&task_type=image"
```

错误码:401。

### 5.7 GET /api/tasks/{task_id}

任务详情;他人任务 403。succeeded 的图像任务额外把 result_url 解析为数组返回 `result_urls`。

响应 200(「示例」,data,图像任务):

```json
{
  "id": 2,
  "task_type": "image",
  "status": "succeeded",
  "prompt": "四川高校校园晚霞,国潮插画风",
  "result_text": null,
  "result_url": "[\"https://dummyimage.com/1024x1024/4f7cff/ffffff.png&text=Mock+Image\"]",
  "result_urls": ["https://dummyimage.com/1024x1024/4f7cff/ffffff.png&text=Mock+Image"],
  "error_message": null,
  "cost": 10,
  "latency_ms": 3210,
  "created_at": "2026-08-29T10:05:00"
}
```

curl:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/tasks/2
```

错误码:401、403(他人任务)、404(任务不存在)。

### 5.8 POST /api/tasks/{task_id}/retry

重试:仅 `failed` 的**异步任务**可重试(文本任务为同步流式,返回 409「请在会话中重新发送」)。重试会重新冻结积分并置回 `pending` 后台执行。

响应 200(「示例」,data):`{ "task_id": 2, "status": "pending" }`

curl:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/tasks/2/retry
```

错误码:401、403(他人任务)、404、409(非失败任务 / 文本任务 / 模型维护中 / 积分不足)。

---

## 6. 上传

### POST /api/uploads

multipart/form-data 上传音频/图片素材。

校验链(全部通过才落盘):

| 校验 | 规则 | 失败返回 |
| --- | --- | --- |
| 扩展名白名单 | mp3 / wav / m4a / png / jpg | 400「不支持的文件类型」 |
| 大小上限 | 10MB | 400「文件超过 10MB 限制」 |
| 文件头魔数 | mp3:ID3/MPEG 帧同步;wav:RIFF;png:\x89PNG;jpg:\xFF\xD8;m4a:ftyp | 400「文件内容与类型不符」 |

响应 200(「示例」,data):

```json
{
  "url": "/static/a1b2c3d4e5f6-clip.mp3",
  "filename": "a1b2c3d4e5f6-clip.mp3",
  "size": 102400
}
```

`url` 可直接填入声音克隆 `sample_audio_url` / 语音识别 `audio_url`;静态访问路径为 `/static/<文件名>`。

curl:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@./clip.mp3" \
  http://127.0.0.1:8000/api/uploads
```

错误码:400(三类校验失败)、401。

---

## 7. 开放平台快速接入

面向校外/第三方系统,提供 OpenAI 兼容的对话接口。**与业务接口不同:成功响应不包统一返回壳,直接返回 OpenAI 兼容结构**;鉴权/限流等失败仍走统一错误结构(见 0.2)。

### 7.1 接口定义

- 路径:`POST /api/chat/completions`(等价别名 `POST /api/v1/chat/completions`)
- 鉴权:`Authorization: Bearer sk-xxx`(API Key,非 JWT)
- 限流:单 Key 每分钟 30 次(`OPENAPI_RATE_LIMIT_PER_MIN`),超限 429
- 仅支持 `model_type=text` 的模型(按 `model` 字段 = models 表 `model_code` 查找,404「模型不存在」/ 409「模型维护中」)
- 每次调用真实扣费(按 models.price_per_call),遵循「冻结→结算→释放」铁律,失败不扣费

请求体(OpenAI 兼容子集):

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| model | string | 是 | 模型调用名,如 "Qwen/Qwen2.5-7B-Instruct" |
| messages | array | 是 | `[{"role":"user","content":"..."}]`,role 支持 system/user/assistant |
| stream | bool | 否 | 默认 false;true 时 SSE 流式 |
| max_tokens | int | 否 | 透传上游 |
| temperature | float | 否 | 透传上游 |

### 7.2 5 分钟接入指南

**第 1 步:生成 API Key。**

Key 管理接口 `POST /api/keys`(成员4 交付)就绪前,可由后端手工生成——用 backend venv 执行:

```bash
cd backend
.venv/Scripts/python -c "from app.core.api_key_auth import generate_api_key; p, prefix, h = generate_api_key(); print(p)"
```

输出的 `sk-<32位hex>` 即明文 Key(**仅此一次展示**)。将其与用户绑定需要写 `api_keys` 表(key_hash=sha256(明文)、key_prefix=前 12 位、user_id、status='enabled'),成员4 的 Key 管理页就绪后改为页面自助创建。

**第 2 步:非流式调用。**

```bash
curl -X POST http://127.0.0.1:8000/api/chat/completions \
  -H "Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": "用一句话介绍四川高校AI大模型门户"}],
    "stream": false,
    "temperature": 0.7
  }'
```

响应 200(「示例」,OpenAI 兼容结构):

```json
{
  "id": "chatcmpl-3f2a9c8e-1c4b-4f6e-9a2d-7b8c1d2e3f4a",
  "object": "chat.completion",
  "created": 1756450000,
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "四川高校AI大模型门户是面向全省高校的统一大模型服务平台。" },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 20, "completion_tokens": 28, "total_tokens": 48 }
}
```

(usage 缺失时按约 2 字符/token 估算。)

**第 3 步:流式调用(`stream: true`)。**

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat/completions \
  -H "Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen/Qwen2.5-7B-Instruct", "messages": [{"role": "user", "content": "你好"}], "stream": true}'
```

SSE 帧格式(`data: {json}\n\n`,结尾固定 `data: [DONE]`):

```text
data: {"id": "chatcmpl-...", "object": "chat.completion.chunk", "model": "Qwen/Qwen2.5-7B-Instruct", "choices": [{"index": 0, "delta": {"content": "你好"}}]}
data: {"id": "chatcmpl-...", "object": "chat.completion.chunk", "model": "Qwen/Qwen2.5-7B-Instruct", "choices": [{"index": 0, "delta": {}}], "finish_reason": "stop"}
data: [DONE]
```

流式失败帧(已退费):

```text
data: {"error": {"message": "生成失败,本次不扣费"}}
data: [DONE]
```

### 7.3 错误码表(开放平台)

| HTTP | code | message | 排查 |
| --- | --- | --- | --- |
| 401 | 40100 | 缺少API Key | 未带 Authorization 头,或值不是 sk- 开头 |
| 401 | 40100 | API Key 无效或已禁用 | Key 哈希查不到 / status≠enabled / 已过期 / 所属用户被禁用;检查 Key 是否抄错、是否被后台禁用 |
| 404 | 40400 | 模型不存在 | model 字段与 models 表 model_code 不一致,或该模型非 text 类型 |
| 409 | 40900 | 模型维护中,暂不可调用 | 模型被管理员停用 |
| 409 | 40900 | 积分不足,请先充值 | Key 所属用户钱包余额 < price_per_call |
| 429 | 42900 | 请求过于频繁,请稍后重试 | 单 Key 60 秒窗口内超 30 次,降低频率或调大 OPENAPI_RATE_LIMIT_PER_MIN |
| 502 | 50200 | 生成失败,本次不扣费 | 上游失败/超时/断连;查看服务端日志按 request_id 排查,冻结积分已退回,可直接重试 |

---

## 附录 A. 扣费铁律说明

所有模型调用(门户任务 + 开放平台)统一遵循:**预扣冻结 → 调用 → 成功结算 → 失败释放**,失败绝不扣费。

| 阶段 | 实现 | 对账口径 |
| --- | --- | --- |
| 冻结 | `billing.freeze`:行锁校验余额,余额不足 409「积分不足,请先充值」;冻结=立即扣减(数据字典 wallets 无冻结列),任务 cost_status=frozen | 任务 cost = models.price_per_call |
| 结算 | `billing.settle`:成功后累计 total_consumed 并写 consumption_records 流水,任务 cost_status=settled | balance 减少量 = settled 任务 cost 之和 |
| 释放 | `billing.refund`:超时/断连/上游异常时等额退回,任务 cost=0、cost_status=refunded | 失败任务 cost 恒为 0 |

验证方式:任意一笔失败任务的 `GET /api/tasks/{id}` 中 `cost=0`;余额只随 succeeded 任务减少(参考 `docs/m-series-result.md` M-04/M-07/M-08 对平结论)。

## 附录 B. Mock 演示模式说明(vendor=mock)

`vendor="mock"` 的模型走 `MockProvider`,**不发起任何外部请求、无需任何 Key、无需 Ollama**,接口链路(流式增量、四态任务、扣费、调用日志)与线上模型完全一致,用于断网/无 Key 环境全链路演示:

- 文本:按「句」流式返回 `【Mock 回复】...`,总延迟默认 2-5s 随机(可用 `models.config_json` 或参数 `mock_delay_sec` 显式指定,全局 `MOCK_DELAY_SEC` 亦可,见 backend/README「Mock 显式延迟」);
- 图像:返回公网样例图 URL(`https://dummyimage.com/...`),数量取 params.num(1..4,默认 2);**断网演示时浏览器加载不到该图**,需按 `backend/assets/samples/README.md` 提前替换 MOCK_IMAGE_URL 或提前下载样例;
- 声音克隆:生成最小可用 MP3 落盘 `/static/clone-mock-*.mp3` 返回本地 URL(离线可用);
- 语音识别:返回固定样例文本「【Mock 识别结果】...」;
- 视频:返回句柄 → 3-5s 后轮询完成,返回公网样例视频 URL(`https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4`,离线需提前下载替换)。

创建 Mock 模型示例(管理员):

```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "Mock 对话(演示)",
    "model_code": "mock-chat",
    "provider_type": "online",
    "model_type": "text",
    "vendor": "mock",
    "price_per_call": 0,
    "description": "无 Key 全链路演示模型"
  }' \
  http://127.0.0.1:8000/api/admin/models
```

## 附录 C. 已登记 TODO

- 线上视频上游查询接口未定:provider 无 `query_video` 时仅空轮询,超 `VIDEO_POLL_MAX_SEC` 判 failed 不扣费(`services/task_service.py` `_poll_video_result`);
- 音视频时长实测依赖 ffprobe,本期仅校验提交方声明的 `duration_sec`(`services/av_service.py` `check_duration`);
- 任务 `elapsed_sec` 时区口径:现按 UTC naive 计算,前端展示前需统一为 UTC+8;
- `providers/base.py` 尚未接入 `app/core/http_client.py` 的共享连接池单例(WP10 登记,后续替换)。
