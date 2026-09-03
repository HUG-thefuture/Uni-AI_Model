# 阿里云百炼 DashScope 大模型接入说明

接入日期：2026-09　｜　目标：采用阿里云免费额度调用大模型（多模态）

## 一、实现方式

新增 `DashScopeProvider`（`backend/app/providers/dashscope.py`），vendor=`dashscope`，与现有
`OnlineProvider`（硅基流动）/`LocalProvider`（Ollama）/`MockProvider` 并行，由 `factory.py` 按
`models.vendor` 分发。密钥走环境变量 `DASHSCOPE_API_KEY`，绝不入库、绝不进 git。

### 接入模型与协议

| 能力 | 模型(model_code) | 协议/端点 | 状态 |
| --- | --- | --- | --- |
| 文本对话 | `qwen-plus` / `qwen-turbo` | OpenAI 兼容 `compatible-mode/v1/chat/completions`（流式 SSE + 非流式） | ✅ 已跑通 |
| 文生图 | `wanx2.1-t2i-turbo` | 原协议异步 `api/v1/services/aigc/text2image/image-synthesis` + `GET /api/v1/tasks/{id}` 轮询 | ✅ 已跑通 |
| 语音合成(TTS) | `qwen-tts` | 原协议 `api/v1/services/aigc/multimodal-generation/generation` | ✅ 已跑通 |
| 语音识别(ASR) | `fun-asr` | 原协议异步 `api/v1/services/audio/asr/transcription`（`file_urls` + 轮询） | ⚠️ 受 Key 权限限制（见下） |

文本走 OpenAI 兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`，与硅基流动协议一致，
复用了同一套流式/非流式解析。图像/语音走百炼原协议 `https://dashscope.aliyuncs.com/api/v1/...`。

## 二、涉及改动

- `backend/app/providers/dashscope.py`（新增，核心 provider）
- `backend/app/providers/factory.py`：注册 `dashscope`
- `backend/app/core/config.py`：新增 `dashscope_api_key` 字段
- `backend/.env.example` / `backend/.env`：新增 `DASHSCOPE_API_KEY`
- `docs/model-config-dashscope.json`（新增，模型种子配置）
- `backend/scripts/seed_dashscope_models.py`（新增，幂等写入 models 表）

## 三、配置与初始化

```bash
# 1. 配置 Key（.env，只存环境变量）
DASHSCOPE_API_KEY=sk-xxx            # 阿里云百炼控制台获取

# 2. 幂等写入 5 个 dashscope 模型到 models 表
cd backend
python scripts/seed_dashscope_models.py

# 3. 启动后端
uvicorn app.main:app --reload --port 8000
```

写入的 5 个模型：qwen-plus / qwen-turbo（text）、wanx2.1-t2i-turbo（image）、
qwen-tts（audio，合成）、fun-asr（audio，识别）。

## 四、端到端验证结果

- 文本非流式（qwen-plus）：✅ 返回完整中文 + usage
- 文本流式（qwen-turbo）：✅ SSE 增量拼接正常
- 文生图（wanx2.1-t2i-turbo）：✅ 异步提交→轮询→下载落盘 `/static/wanx_*.png`
- 语音合成（qwen-tts）：✅ 返回音频落盘 `/static/tts_*.wav`
- 语音识别（fun-asr）：⚠️ 当前 `sk-ws-` 工作区 Key 返回 403 `AccessDenied`，未开通语音识别服务

## 五、ASR 权限限制（重要）

当前使用的 Key 是 `sk-ws-` 前缀的**工作区密钥**，已验证：文本/图像/语音合成可用，但
**语音识别(ASR)未开通权限**，调用返回 `403 current user api does not support synchronous calls`。

要真正跑通 ASR，需要：
1. 在百炼控制台为该工作区/账号开通**语音识别**模型（fun-asr / paraformer-v1 / sensevoice-v1）；或
2. 换用已开通语音识别服务的普通百炼 API Key（`sk-` 开头，非 `sk-ws-`）。

此外，百炼 ASR 采用**异步任务 + `file_urls`（公网可下载 URL）**协议，不支持本地二进制直传；
本地 `/static/` 音频需先上传到 OSS/公网才能识别（provider 内已做对应校验与中文报错提示）。

## 六、遗留事项

- ASR 实际可用依赖账号开通语音识别权限（外部条件，非代码问题）。
- `dashscope.py` 的 `generate_video` 本期未接入（抛 `provider_not_ready`），视频可继续用 siliconflow 或 Mock 演示。
- 若需在本地 8000 端口让最新 ASR 代码生效，需重启后端进程（当前运行中的后端可能仍是修正前的 ASR 实现）。