"""部署初始化入口：建表并同步全部模型种子（含阿里百炼 DashScope）。

在 backend 目录执行：``python -m app.init_all``
一条命令即可拿到最新模型数据：幂等建表 + 聚合同步 docs/ 下全部模型模板
（scripts/seed_models.py 的 TEMPLATE_PATHS，新增模板在清单里追加即可）。
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
