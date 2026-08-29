"""会话路由(WP04):路径不含 /api 前缀,main.py 统一挂 /api 与 /api/v1。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.response import ok
from app.models.support import User
from app.schemas.chat import ChatSessionCreate
from app.services import chat_service

router = APIRouter(tags=["chat"])


@router.post("/chat/sessions")
def create_chat_session(body: ChatSessionCreate,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """创建会话:校验模型存在且 enabled;title 先「新会话」,首条消息后更新为前 20 字。"""
    model = chat_service.get_enabled_model(db, body.model_id)
    session = chat_service.create_session(db, user.id, model)
    return ok({
        "session_id": session.id,
        "title": session.title,
        "model_id": session.model_id,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    })


@router.get("/chat/sessions")
def list_chat_sessions(page: int = Query(1, ge=1),
                       page_size: int = Query(10, ge=1, le=100),
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """我的会话分页,按 updated_at 倒序。"""
    total, rows = chat_service.list_sessions(db, user.id, page, page_size)
    return ok({
        "total": total, "page": page, "page_size": page_size,
        "items": [{
            "session_id": s.id,
            "title": s.title,
            "model_id": s.model_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        } for s in rows],
    })


@router.get("/chat/sessions/{session_id}/messages")
def list_session_messages(session_id: int,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """历史消息按 created_at 正序;他人会话 403。"""
    session = chat_service.get_owned_session(db, user.id, session_id)
    rows = chat_service.list_messages(db, session.id)
    return ok({
        "session_id": session.id,
        "title": session.title,
        "items": [{
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "model_id": m.model_id,
            "tokens_used": m.tokens_used,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in rows],
    })
