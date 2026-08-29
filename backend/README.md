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
