"""初始化入口(一步到位):建表 + 写入全部模型种子。

在 backend/ 目录执行:

    python -m app.init_db                # 建表 + 幂等写入 docs/ 全部模型模板(推荐)
    python -m app.init_db --schema-only  # 仅建表,不写模型种子(兼容旧口径)

模型模板在仓库根 docs/ 下(model-config-*.json,含阿里百炼 dashscope 5 个模型)。
新增厂商模型只需在 docs/ 加一个模板 JSON:其他人 git pull 后执行本命令,
即可拿到最新模型数据,无需改代码、无需再单独跑 seed 脚本。
"""
import sys

from .core.db import Base, init_db as create_tables
from .model_seed import seed_all_models


def main() -> int:
    """默认一步初始化(建表 + 全量模型种子);--schema-only 仅建表。"""
    if "--schema-only" in sys.argv[1:]:
        report = create_tables()
        print("建表/结构对齐完成(未写模型种子):" + ", ".join(sorted(Base.metadata.tables)))
        print(f"[init] 新增列 {len(report.added_columns)}，新增索引 {len(report.created_indexes)}")
        return 0
    try:
        result = seed_all_models()
    except Exception as exc:  # noqa: BLE001 环境变量缺失/模板缺失给出明确提示
        print(f"[init] 初始化失败: {exc}", file=sys.stderr)
        print("[init] 请在 backend/ 目录下执行,并确认 .env 已配置 DATABASE_URL / SECRET_KEY",
              file=sys.stderr)
        return 1
    report = result.pop("schema_report", None)
    schema_message = ""
    if report is not None:
        schema_message = (f"; 结构新增列 {len(report.added_columns)}、"
                          f"索引 {len(report.created_indexes)}")
    print(f"[init] 初始化完成: 建表 {len(Base.metadata.tables)} 张; "
          f"模型共 {result['total']} 个(新增 {result['created']}, 更新 {result['updated']}), "
          f"模板: {', '.join(result['files'])}{schema_message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
