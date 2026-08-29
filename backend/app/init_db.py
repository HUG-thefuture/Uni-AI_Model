"""建表入口:python -m app.init_db(在 backend/ 目录下执行)。

创建成员2负责的 models / ai_tasks / ai_call_logs 三张表;
users 等成员1/4 的表请使用 sql/ 目录下的建表 SQL。
"""
from app.core.db import init_db

if __name__ == "__main__":
    init_db()
    print("建表完成:models / ai_tasks / ai_call_logs")
