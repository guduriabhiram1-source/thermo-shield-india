"""ADMIN user management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.security import require_admin, revoke_all_refresh_tokens
from ..database import get_db
from ..models import User
from ..schemas import UserOut, UserUpdateRequest
from ..services.audit import log_action
from .auth import user_out

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), limit: int = Query(default=200, ge=1, le=1000)):
    return [user_out(u) for u in db.execute(select(User).order_by(User.created_at.desc()).limit(limit)).scalars().all()]


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdateRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if u.id == admin.id and (body.role not in (None, "ADMIN") or body.is_active is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot demote or deactivate your own account")
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(u, k, int(v) if isinstance(v, bool) else v)
    if body.is_active is False:
        revoke_all_refresh_tokens(db, u.id)
    log_action(db, admin.email, "update_user", "user", u.id, changes)
    db.commit()
    return user_out(u)
