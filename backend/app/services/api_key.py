from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.api_key import ApiKey
import secrets
import hashlib

def create_raw_api_key()->str:
    raw_key="sk-"+secrets.token_urlsafe(32)
    return raw_key

def hash_api_key(raw_key:str)->str:
    return hashlib.sha256(raw_key.encode()).hexdigest()

def get_key_prefix(raw_key:str)->str:
    return raw_key[:12]

async def create_api_keys(db:AsyncSession,user_id:int,name:str)->ApiKey:
    raw_key=create_raw_api_key()

    new_key=ApiKey(
        user_id=user_id,
        name=name,
        key_hash=hash_api_key(raw_key),
        key_prefix=get_key_prefix(raw_key),
        status="enabled",
        use_count=0
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    new_key._raw_key = raw_key
    return new_key

async def get_api_keys(db:AsyncSession,user_id:int)->list[ApiKey]:
    stmt=select(ApiKey).where(ApiKey.user_id == user_id)
    keys=(await db.scalars(stmt)).all()
    return list(keys)


async def update_api_keys(db:AsyncSession,user_id:int,key_id:int,status:str)->ApiKey | None:
    stmt=select(ApiKey).where(ApiKey.id==key_id,ApiKey.user_id == user_id)
    key=(await db.scalar(stmt))
    if not key:
        return None

    key.status=status
    await db.commit()
    await db.refresh(key)
    return key

