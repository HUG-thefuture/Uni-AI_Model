"""部署初始化入口：建表并同步模型种子。

在 backend 目录执行：``python -m app.init_all``
命令可重复执行，不会删除数据；模型按 model_code + provider_type 幂等更新。
"""
import sys

from app.bootstrap import initialize_database


def main() -> int:
    try:
        result = initialize_database(seed_if_empty=False)
    except Exception as exc:  # noqa: BLE001
        print(f"初始化失败: {exc}", file=sys.stderr)
        return 1
    print(f"初始化完成，共 {len(result['tables'])} 张表，模型同步 {result['models']} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
