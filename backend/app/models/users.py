from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="VIEWER", index=True)  # ADMIN | ANALYST | VIEWER
    organisation: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    is_verified: Mapped[int] = mapped_column(Integer, default=0, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class EmailVerification(Base):
    """One-time e-mail verification codes (hashed) with expiry - the second step of sign-up."""

    __tablename__ = "email_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(32), default="signup")  # signup | login_2fa | password_reset
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(32), default="pending")  # sent | failed | logged | pending
    delivery_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(254), default="system")
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    details: Mapped[dict | None] = mapped_column(JSON, default=None)
    note: Mapped[str] = mapped_column(Text, default="")
