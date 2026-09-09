"""回填历史任务的 token 用量统计。

token 列(prompt_tokens/completion_tokens)于 2026-09-07 上线,此前成功的文本任务
没有用量记录,导致个人中心「用量统计」与历史账单里 token 总量为 0。

对 status='succeeded' 且 prompt_tokens IS NULL 的文本任务,按全站统一估算口径
(2 字符 ≈ 1 token,见 services/pricing.py)从已落库的 prompt / result_text 估算:
  prompt_tokens     = max(1, len(prompt) // 2)
  completion_tokens = max(1, len(result_text) // 2)
费用(cost)不重算——历史订单按当时口径结算,保持台账不变,只补统计口径。

用法(backend 目录、venv 下执行):
  python scripts/backfill_task_tokens.py            # 预览将回填的任务
  python scripts/backfill_task_tokens.py --apply    # 实际写入
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.models.ai_task import AiTask  # noqa: E402
from app.services.pricing import estimate_tokens  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="回填历史文本任务的 token 用量")
    parser.add_argument("--apply", action="store_true", help="实际写入(默认仅预览)")
    args = parser.parse_args()

    with SessionLocal() as db:
        tasks = db.execute(
            select(AiTask)
            .where(
                AiTask.status == "succeeded",
                AiTask.task_type == "text",
                AiTask.prompt_tokens.is_(None),
            )
            .order_by(AiTask.id)
        ).scalars().all()

        if not tasks:
            print("没有需要回填的任务(token 统计完整)")
            return

        print(f"{'ID':<6}{'用户':<8}{'模型':<8}{'入tokens':<10}{'出tokens':<10}创建时间")
        total_in = total_out = 0
        for t in tasks:
            prompt_tokens = estimate_tokens(getattr(t, "prompt", None))
            completion_tokens = estimate_tokens(getattr(t, "result_text", None))
            total_in += prompt_tokens
            total_out += completion_tokens
            print(f"{t.id:<6}{t.user_id:<8}{t.model_id:<8}{prompt_tokens:<10}{completion_tokens:<10}{t.created_at}")
            if args.apply:
                t.prompt_tokens = prompt_tokens
                t.completion_tokens = completion_tokens

        if args.apply:
            db.commit()
            print(f"已回填 {len(tasks)} 条任务,合计 入={total_in} 出={total_out} tokens")
        else:
            print(f"预览 {len(tasks)} 条(未写入)。确认无误后加 --apply 执行。")


if __name__ == "__main__":
    main()
