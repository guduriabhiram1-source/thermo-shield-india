"""Password hashing (Argon2id), JWT access tokens, refresh tokens, verification
codes and role-based authorisation (ADMIN > ANALYST > VIEWER)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import RefreshToken, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
ROLE_RANK = {"VIEWER": 1, "ANALYST": 2, "ADMIN": 3}
ROLES = ("ADMIN", "ANALYST", "VIEWER")
_hasher = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)


# --- passwords ---------------------------------------------------------------
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, ValueError):
        return False


def password_policy_errors(password: str) -> list[str]:
    errors = []
    if len(password) < 10:
        errors.append("at least 10 characters")
    if not any(c.isdigit() for c in password):
        errors.append("at least one digit")
    if not any(c.isalpha() for c in password):
        errors.append("at least one letter")
    return errors


# --- verification codes / opaque tokens ------------------------------------
def generate_verification_code() -> str:
    """6-digit numeric code from the OS CSPRNG (typed by the user from Gmail)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str, salt: str) -> str:
    return hmac.new(settings.jwt_secret.encode("utf-8"), f"{salt}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- JWT ----------------------------------------------------------------------
def create_access_token(user: User, expires_minutes: int | None = None) -> tuple[str, int]:
    minutes = expires_minutes or settings.access_token_expire_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": str(user.id), "email": user.email, "role": user.role, "type": "access", "exp": expire, "iat": datetime.now(timezone.utc), "jti": secrets.token_hex(8)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), minutes * 60


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
    return payload


def issue_refresh_token(db: Session, user: User, user_agent: str = "") -> str:
    raw = generate_opaque_token()
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(raw), user_agent=user_agent[:256],
                        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)))
    return raw


def consume_refresh_token(db: Session, raw: str) -> User:
    rec = db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if rec is None or rec.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalid or revoked")
    exp = rec.expires_at if rec.expires_at.tzinfo else rec.expires_at.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")
    rec.revoked_at = now  # rotation: every refresh token is single use
    user = db.get(User, rec.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return user


def revoke_refresh_token(db: Session, raw: str) -> bool:
    rec = db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))).scalar_one_or_none()
    if rec and rec.revoked_at is None:
        rec.revoked_at = datetime.now(timezone.utc)
        return True
    return False


def revoke_all_refresh_tokens(db: Session, user_id: int) -> int:
    n = 0
    for rec in db.execute(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))).scalars().all():
        rec.revoked_at = datetime.now(timezone.utc)
        n += 1
    return n


# --- dependencies -------------------------------------------------------------
def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    payload = decode_token(token)
    user = db.get(User, int(payload.get("sub", 0) or 0))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    if not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email verification required")
    return user


def get_optional_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User | None:
    if not token:
        return None
    try:
        return get_current_user(token, db)
    except HTTPException:
        return None


def require_role(minimum: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {minimum} role or higher")
        return user

    return dependency


require_viewer = require_role("VIEWER")
require_analyst = require_role("ANALYST")
require_admin = require_role("ADMIN")


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
