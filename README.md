# AI 大模型门户（ai-portal）

四川高校 AI 大模型门户 · 四人项目组

- 开发周期：2026-08-29 至 2026-09-03（9/4 路演）
- 技术栈：前端 HTML/CSS/JavaScript/Ajax/jQuery/Layui；后端 Python/FastAPI/SQLAlchemy/MySQL；Linux + 宝塔部署
- 仓库归属：mac/Uni-AI_Model（私有）

## 目录规划（建议）

```text
ai-portal/
├── backend/        # FastAPI 后端（成员2/4）
├── frontend/       # Layui 前端页面（成员3）
├── docs/           # 数据字典、接口约定表、部署文档等
├── sql/            # 数据库脚本
└── scripts/        # 备份、部署脚本
```

## 今日交付（8/29 成员1）

- [docs/数据字典.md](docs/数据字典.md)：users / user_profiles / wallets 字段、约束、关系与建表 SQL
- [docs/接口约定表.md](docs/接口约定表.md)：统一返回结构、错误码、权限矩阵及成员1 的 7 个接口
- [docs/项目框架与任务分工.md](docs/项目框架与任务分工.md)：总体架构、目录框架、四人任务落实
