"""建表入口：在 backend/ 目录执行 ``python -m app.init_db``。"""
from .core.db import Base, init_db

if __name__ == "__main__":
    init_db()
    print("建表完成:" + ", ".join(sorted(Base.metadata.tables)))
