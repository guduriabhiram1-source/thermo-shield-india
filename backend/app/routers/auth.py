"""Registration → Gmail verification code → login (JWT) → refresh → logout."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.rate_limit import RateLimiter, limiter_dependency
from ..auth.security import (
    consume_refresh_token, create_access_token, generate_verification_code, get_current_user, hash_code, hash_password,
    issue_refresh_token, password_policy_errors, revoke_all_refresh_tokens, revoke_refresh_token, verify_password,
)
from ..config import settings
from ..database import get_db
from ..models import EmailVerification, User
from ..schemas import (
    LoginRequest, LogoutRequest, MessageResponse, RefreshRequest, RegisterRequest, ResendVerificationRequest, TokenResponse, UserOut,
    VerifyEmailRequest,
)
from ..services import email_service
from ..services.audit import log_action

log = logging.getLogger("thermoshield.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])
auth_limiter = RateLimiter(settings.auth_rate_limit_per_minute)
_limit = limiter_dependency(auth_limiter, "auth")


def user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, full_name=u.full_name, role=u.role, organisation=u.organisation, is_verified=bool(u.is_verified),
                   is_active=bool(u.is_active), created_at=u.created_at, last_login_at=u.last_login_at)


def _issue_code(db: Session, user: User, purpose: str = "signup") -> tuple[EmailVerification, str]:
    """Invalidate previous codes, create a fresh one and e-mail it. Returns the record + delivery status."""
    now = datetime.now(timezone.utc)
    for old in db.execute(select(EmailVerification).where(EmailVerification.user_id == user.id, EmailVerification.consumed_at.is_(None))).scalars().all():
        old.consumed_at = now
    code = generate_verification_code()
    rec = EmailVerification(user_id=user.id, email=user.email, code_hash=hash_code(code, user.email), purpose=purpose,
                            expires_at=now + timedelta(minutes=settings.verification_code_expire_minutes))
    db.add(rec)
    db.flush()
    result = email_service.verification_email(user.email, code, purpose)
    rec.delivery_status = result.status
    rec.delivery_error = result.detail if result.status in ("failed", "not_configured") else ""
    if result.status == "failed":
        log.error("Verification e-mail to %s failed: %s", user.email, result.detail)
    return rec, result.status


def _delivery_message(status_: str) -> str:
    return {
        "sent": "Verification code sent - check your Gmail inbox (and spam folder).",
        "logged": "E-mail delivery is in development log-only mode: the code was written to the backend log.",
        "not_configured": "E-mail delivery is not configured on this server (SMTP settings missing). Contact the administrator.",
        "failed": "The verification e-mail could not be delivered. Try 'Resend verification code' or contact the administrator.",
    }.get(status_, status_)


def _assign_role(db: Session, email: str) -> str:
    if email.lower() in settings.bootstrap_admin_list:
        return "ADMIN"
    if settings.first_user_is_admin and (db.execute(select(func.count(User.id))).scalar() or 0) == 0:
        return "ADMIN"
    return "VIEWER"


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(_limit)])
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    if settings.allowed_email_domains:
        domains = [d.strip().lower() for d in settings.allowed_email_domains.split(",") if d.strip()]
        if email.split("@")[-1] not in domains:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Registrations are restricted to approved e-mail domains")
    errors = password_policy_errors(body.password)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password must contain " + ", ".join(errors))
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        if existing.is_verified:
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this e-mail already exists - sign in instead")
        # unverified account: allow re-registration to update password and re-send the code
        existing.hashed_password = hash_password(body.password)
        existing.full_name = body.full_name or existing.full_name
        existing.organisation = body.organisation or existing.organisation
        rec, delivery = _issue_code(db, existing)
        db.commit()
        return MessageResponse(message="Account exists but is not verified - a new verification code has been issued.", detail=_delivery_message(delivery))
    user = User(email=email, full_name=body.full_name.strip(), organisation=body.organisation.strip(), hashed_password=hash_password(body.password),
                role=_assign_role(db, email), is_active=1, is_verified=0)
    db.add(user)
    db.flush()
    rec, delivery = _issue_code(db, user)
    log_action(db, email, "register", "user", user.id, {"role": user.role, "email_delivery": delivery})
    db.commit()
    return MessageResponse(message="Account created. Verify your e-mail address to activate it.", detail=_delivery_message(delivery))


@router.post("/verify-email", response_model=MessageResponse, dependencies=[Depends(_limit)])
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account found for this e-mail")
    if user.is_verified:
        return MessageResponse(message="E-mail already verified - you can sign in.")
    now = datetime.now(timezone.utc)
    rec = db.execute(select(EmailVerification).where(EmailVerification.user_id == user.id, EmailVerification.consumed_at.is_(None))
                     .order_by(EmailVerification.created_at.desc())).scalars().first()
    if rec is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No active verification code - request a new one")
    exp = rec.expires_at if rec.expires_at.tzinfo else rec.expires_at.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Verification code expired (valid {settings.verification_code_expire_minutes} minutes) - request a new one")
    if rec.attempts >= 5:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many incorrect attempts - request a new code")
    rec.attempts += 1
    if rec.code_hash != hash_code(body.code, user.email):
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect verification code")
    rec.consumed_at = now
    user.is_verified = 1
    user.verified_at = now
    log_action(db, user.email, "verify_email", "user", user.id)
    db.commit()
    return MessageResponse(message="E-mail verified - your account is active. You can now sign in.")


@router.post("/resend-verification", response_model=MessageResponse, dependencies=[Depends(_limit)])
def resend_verification(body: ResendVerificationRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    # do not reveal whether an account exists
    if user is None or user.is_verified:
        return MessageResponse(message="If an unverified account exists for this e-mail, a new code has been sent.")
    last = db.execute(select(EmailVerification).where(EmailVerification.user_id == user.id).order_by(EmailVerification.created_at.desc())).scalars().first()
    if last is not None:
        created = last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=timezone.utc)
        wait = settings.verification_resend_cooldown_seconds - (datetime.now(timezone.utc) - created).total_seconds()
        if wait > 0:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Please wait {int(wait)} s before requesting another code")
    _, delivery = _issue_code(db, user)
    log_action(db, user.email, "resend_verification", "user", user.id, {"email_delivery": delivery})
    db.commit()
    return MessageResponse(message="A new verification code has been issued.", detail=_delivery_message(delivery))


def _login(db: Session, email: str, password: str, user_agent: str) -> TokenResponse:
    email = email.lower().strip()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        if user is not None:
            user.failed_logins += 1
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid e-mail or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is deactivated - contact the administrator")
    if not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email verification required - enter the code sent to your Gmail address (or request a new one)")
    user.failed_logins = 0
    user.last_login_at = datetime.now(timezone.utc)
    access, expires = create_access_token(user)
    refresh = issue_refresh_token(db, user, user_agent)
    log_action(db, user.email, "login", "user", user.id)
    db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, expires_in=expires, user=user_out(user))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(_limit)])
def login_json(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return _login(db, body.email, body.password, request.headers.get("user-agent", ""))


@router.post("/token", response_model=TokenResponse, include_in_schema=True, dependencies=[Depends(_limit)])
def login_form(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2 password-flow form login (used by the Swagger 'Authorize' button; username = e-mail)."""
    return _login(db, form.username, form.password, request.headers.get("user-agent", ""))


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(_limit)])
def refresh(body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    user = consume_refresh_token(db, body.refresh_token)
    access, expires = create_access_token(user)
    new_refresh = issue_refresh_token(db, user, request.headers.get("user-agent", ""))
    db.commit()
    return TokenResponse(access_token=access, refresh_token=new_refresh, expires_in=expires, user=user_out(user))


@router.post("/logout", response_model=MessageResponse)
def logout(body: LogoutRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = 0
    if body.all_devices:
        n = revoke_all_refresh_tokens(db, user.id)
    elif body.refresh_token:
        n = 1 if revoke_refresh_token(db, body.refresh_token) else 0
    log_action(db, user.email, "logout", "user", user.id, {"revoked": n})
    db.commit()
    return MessageResponse(message="Signed out", detail=f"{n} refresh token(s) revoked")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_out(user)
