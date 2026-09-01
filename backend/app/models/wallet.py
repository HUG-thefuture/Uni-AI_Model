"""wallets 表 ORM。

Wallet 的唯一定义在 user.py(与 users/user_profiles 同文件,__init__.py 从那里注册到 Base.metadata);
本模块仅重导出,避免 wallets 表在同一个 MetaData 里被重复定义导致 SQLAlchemy 报错。
"""
from .user import Wallet

__all__ = ["Wallet"]
