"""图像/视频模型成本价对齐官方文档(2026-09-07 核对)。

变更:
1. models.price_per_call 列类型 BigInteger → DECIMAL(10,4),语义升级为
   「供应商成本单价(元/张·条·次)」;用户售价 = 成本 × 加价比例(TOKEN_MARKUP_PCT,
   默认 130 = 加价 30%),与 token 计费同口径盈利。
2. 按官方计费公式更新成本价(阿里云百炼:费用 = 单价 × 图片张数;
   硅基流动:视频按条计费):
   - stabilityai/stable-diffusion-3-5-large  0.25 元/张(官方早期牌价/第三方整理,
     该型号在官方价格页的在线状态以实时页为准)
   - Qwen/Qwen-Image                          0.30 元/张
   - Kwai-Kolors/Kolors                       0.14 元/张
   - wanx2.1-t2i-turbo(百炼)                  0.14 元/张
   - Wan-AI/Wan2.2-T2V-A14B                   2.00 元/条
   - Wan-AI/Wan2.2-I2V-A14B                   2.00 元/条

用法:python scripts/update_media_prices.py --apply(默认仅预览)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.db import engine  # noqa: E402

# (model_code, 成本单价 元/张·条)
PRICES = {
    "stabilityai/stable-diffusion-3-5-large": 0.25,
    "Qwen/Qwen-Image": 0.30,
    "Kwai-Kolors/Kolors": 0.14,
    "wanx2.1-t2i-turbo": 0.14,
    "Wan-AI/Wan2.2-T2V-A14B": 2.00,
    "Wan-AI/Wan2.2-I2V-A14B": 2.00,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="图像/视频模型成本价对齐官方文档")
    parser.add_argument("--apply", action="store_true", help="实际执行(默认仅预览)")
    args = parser.parse_args()

    with engine.begin() as conn:
        cols = conn.execute(text("SHOW COLUMNS FROM `models` LIKE 'price_per_call'")).first()
        print("当前列类型:", cols[1] if cols else "(missing)")
        rows = conn.execute(text(
            "SELECT id, model_code, price_per_call FROM models "
            "WHERE model_code IN :codes ORDER BY id"
        ), {"codes": tuple(PRICES)}).all()
        for r in rows:
            print(f"  #{r[0]} {r[1]}: {r[2]} → {PRICES[r[1]]}")

        if not args.apply:
            print("预览完成(未写入)。确认后加 --apply 执行。")
            return

        if cols and "decimal" not in str(cols[1]).lower():
            conn.execute(text(
                "ALTER TABLE `models` MODIFY COLUMN `price_per_call` DECIMAL(10,4) "
                "NOT NULL DEFAULT '0.0000' COMMENT '供应商成本单价(元/张·条·次,4位小数);per_call 时生效,售价=成本×加价'"
            ))
            print("列类型已改为 DECIMAL(10,4)")
        for code, price in PRICES.items():
            conn.execute(
                text("UPDATE `models` SET `price_per_call` = :p WHERE `model_code` = :c"),
                {"p": price, "c": code},
            )
        print("成本价更新完成,售价将按 加价比例 自动计算。")


if __name__ == "__main__":
    main()
