# AI 大模型门户 · 多模型AI服务平台

面向高校用户的一站式 AI 多模态门户：模型广场、文本对话（SSE 流式）、图像 / 声音克隆 / 语音识别 / 视频生成四类异步任务、开放平台（OpenAI 兼容接口）。四人团队项目，本人在其中担任**后端负责人（成员2）**，负责模型供应商接入层与核心接口。

- **在线体验**：<https://aigc.aitoolcore.com>（已上线）
- **开发周期**：2026-08-29 起（9/4 路演交付，随后迭代至 9/9）
- **技术栈**：Python 3.11 / FastAPI / SQLAlchemy 2.0 / MySQL 8 / httpx / PyJWT / pytest；前端 HTML/CSS/JS/jQuery/Layui；Linux + 宝塔部署

## 后端架构亮点（本人负责）

- **供应商适配层**：`BaseProvider` 抽象 6 个 async 能力方法（流式文本 / 图像 / 声音克隆 / 语音识别 / 视频 / 探活），统一接入 DashScope（阿里百炼）、OpenAI 兼容（硅基流动等）、Ollama 与 Mock 供应商——新增供应商不改业务代码，密钥只走环境变量、绝不入库。
- **核心接口**：文本 SSE 流式对话；四类生成任务异步四态流转（提交 → 轮询）；OpenAI 兼容开放接口（API Key 鉴权 + 限流）。
- **数据与可观测**：`models / ai_tasks / ai_call_logs` 三表建模 + 编号式迁移 SQL；`request_id` 全链路贯穿并落库；`GET /api/health` 健康探针。
- **计费一致性**：统一计价 `pricing`（按模型 × 媒体类型）；钱包三态流转（冻结 → 结算 → 释放）+ 行锁；失败任务一律退费；**启动补偿**——进程重启后把滞留在冻结态的资金统一退回。
- **稳定性验证**：M-01 ~ M-08 稳定性用例 **8/8 PASS**（超时 / 模型停用联动 / 重复提交 / 50 并发 0 个 500、扣费与流水精确对平）。
- **配套能力**：短信验证码登录（阿里云 SMS）、支付宝充值、发票与账单、管理后台。

## 目录结构

```text
├── backend/        # FastAPI 后端（供应商适配层 / 任务 / 钱包计费 / 开放接口）
│   ├── app/        # core / models / schemas / routers / services / providers
│   ├── tests/      # 接口与稳定性用例（含计费定价、支付、短信）
│   └── .env.example
├── frontend/       # Layui 前端页面（模型广场 / 对话 / 任务 / 管理后台）
├── docs/           # 数据字典、接口约定表、部署文档、成员交付总览
├── sql/            # 建表与迁移脚本
└── scripts/        # 备份、部署脚本
```

## 快速开始（后端）

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # 填好 DATABASE_URL / SECRET_KEY；供应商 Key 均走环境变量
python -m app.init_db       # 一步初始化：建表 + 模型种子（幂等）
uvicorn app.main:app --reload --port 8000
# 探针: curl http://127.0.0.1:8000/api/health
```

未配置任何供应商 Key 时可用 Mock 供应商全链路演示。测试：`pytest`（backend/tests/，含 M-01~M-08 稳定性用例）。

## 分支说明

- `master`：9/4 路演交付基线
- `test1`：持续迭代线——短信验证码登录、支付宝充值、统一计价与 token 统计、启动补偿

## 团队与协作

四人项目组：接口约定表与数据字典先行、每日集成测试、交付留证。分工见 `docs/项目框架与任务分工.md`；本人交付记录见 `docs/成员2-交付总览.md`。
