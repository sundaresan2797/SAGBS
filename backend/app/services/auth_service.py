import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessRuleError, RateLimitError, UnauthorizedError
from app.core.redis import CacheKeys, redis_service
from app.core.security import TokenType, create_token, decode_token, hash_password, verify_password
from app.models.employee import Employee
from app.models.enums import AuditAction
from app.models.user import PasswordResetToken, User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse
from app.schemas.user import UserOut
from app.services.audit_service import log_action

logger = logging.getLogger("ems.auth")

RESET_TOKEN_TTL_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _check_login_rate_limit(identifier: str) -> None:
    key = CacheKeys.login_rate_limit(identifier)
    attempts = await redis_service.incr(key, ttl_seconds=settings.rate_limit_login_window_seconds)
    if attempts is not None and attempts > settings.rate_limit_login_attempts:
        raise RateLimitError(
            "Too many login attempts. Please try again later.", error_code="LOGIN_RATE_LIMITED"
        )


async def build_user_out(session: AsyncSession, user: User) -> UserOut:
    result = await session.execute(select(Employee.id).where(Employee.user_id == user.id))
    employee_id = result.scalar_one_or_none()
    permissions = sorted({permission.code for permission in user.role.permissions})
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role.name,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        employee_id=employee_id,
        permissions=permissions,
    )


async def login(session: AsyncSession, email: str, password: str, request: Request | None = None) -> TokenResponse:
    await _check_login_rate_limit(email.lower())

    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(email)

    if user is None or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password.", error_code="INVALID_CREDENTIALS")

    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated.", error_code="ACCOUNT_INACTIVE")

    user.last_login_at = datetime.now(timezone.utc)
    await session.flush()

    access_token = create_token(str(user.id), TokenType.ACCESS, {"role": user.role.name, "tv": user.token_version})
    refresh_token = create_token(str(user.id), TokenType.REFRESH, {"tv": user.token_version})

    await log_action(
        session,
        user_id=user.id,
        action=AuditAction.LOGIN,
        entity_type="User",
        entity_id=user.id,
        description=f"User {user.email} logged in",
        request=request,
    )
    await session.commit()

    user_out = await build_user_out(session, user)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=user_out)


async def refresh_access_token(session: AsyncSession, refresh_token: str) -> str:
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != TokenType.REFRESH.value:
        raise UnauthorizedError("Invalid or expired refresh token.", error_code="INVALID_REFRESH_TOKEN")

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or expired refresh token.", error_code="INVALID_REFRESH_TOKEN")
    if payload.get("tv") != user.token_version:
        raise UnauthorizedError(
            "This session is no longer valid. Please sign in again.", error_code="INVALID_REFRESH_TOKEN"
        )

    return create_token(str(user.id), TokenType.ACCESS, {"role": user.role.name, "tv": user.token_version})


async def _check_password_reset_rate_limit(identifier: str) -> None:
    key = CacheKeys.password_reset_rate_limit(identifier)
    attempts = await redis_service.incr(key, ttl_seconds=settings.rate_limit_login_window_seconds)
    if attempts is not None and attempts > settings.rate_limit_login_attempts:
        raise RateLimitError(
            "Too many password reset requests. Please try again later.", error_code="PASSWORD_RESET_RATE_LIMITED"
        )


async def request_password_reset(session: AsyncSession, email: str) -> None:
    await _check_password_reset_rate_limit(email.lower())

    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(email)

    # Always behave the same way whether or not the email exists, to avoid
    # leaking which addresses have accounts.
    if user is None:
        return

    raw_token = secrets.token_urlsafe(32)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
    )
    session.add(reset_token)
    await session.commit()

    # V1 has no email/SMTP integration (out of scope per spec); logging the
    # reset link lets this flow be tested end-to-end in development. Wire a
    # real mail provider here in V2 without touching the rest of this flow.
    logger.info("Password reset requested for %s. Dev reset token: %s", email, raw_token)


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    token_hash = _hash_token(token)
    result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    reset_token = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if reset_token is None or reset_token.used_at is not None or reset_token.expires_at < now:
        raise BusinessRuleError("This reset link is invalid or has expired.", error_code="INVALID_RESET_TOKEN")

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(reset_token.user_id)
    if user is None:
        raise BusinessRuleError("This reset link is invalid or has expired.", error_code="INVALID_RESET_TOKEN")

    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    user.token_version += 1
    reset_token.used_at = now
    await session.commit()


async def change_password(session: AsyncSession, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise BusinessRuleError("Current password is incorrect.", error_code="INVALID_CURRENT_PASSWORD")
    # Otherwise someone told to replace a temporary password could "change" it to the same one and lift the lock.
    if new_password == current_password:
        raise BusinessRuleError(
            "Your new password must be different from your current one.", error_code="PASSWORD_UNCHANGED"
        )

    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    user.token_version += 1
    await session.commit()
