"""管理员角色管理脚本:查看 / 授予 / 撤销指定用户的 admin 角色。

用法(在 backend 目录、激活 venv 后执行):
  python scripts/set_admin.py --list                 # 列出全部用户与角色
  python scripts/set_admin.py --grant admin          # 把用户 admin 提升为管理员
  python scripts/set_admin.py --revoke somebody      # 撤销某用户的管理员
角色变更立即生效(下一次登录/鉴权即按新角色判定),无需重启服务。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def list_users() -> None:
    with SessionLocal() as db:
        users = db.query(User).order_by(User.id).all()
        if not users:
            print("库中暂无用户")
            return
        print(f"{'ID':<6}{'用户名':<24}{'角色':<10}{'状态'}")
        for u in users:
            status = "启用" if u.status == 1 else "禁用"
            print(f"{u.id:<6}{u.username:<24}{u.role:<10}{status}")


def set_role(username: str, role: str) -> None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user is None:
            print(f"用户 {username!r} 不存在;可用用户见 --list")
            raise SystemExit(1)
        if user.role == role:
            print(f"用户 {username!r} 已是 {role},无需变更")
            return
        user.role = role
        db.commit()
        print(f"已把用户 {username!r} 的角色变更为 {role}(立即生效)")


def main() -> None:
    parser = argparse.ArgumentParser(description="管理员角色管理")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="列出全部用户与角色")
    group.add_argument("--grant", metavar="USERNAME", help="授予管理员角色")
    group.add_argument("--revoke", metavar="USERNAME", help="撤销管理员角色")
    args = parser.parse_args()
    if args.list:
        list_users()
    elif args.grant:
        set_role(args.grant, "admin")
    elif args.revoke:
        set_role(args.revoke, "user")


if __name__ == "__main__":
    main()
