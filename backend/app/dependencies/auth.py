from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import TokenType, decode_token
from app.database.session import get_db
from app.models.enums import RoleName
from app.models.user import User
from app.repositories.user_repository import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Authentication required.", error_code="MISSING_TOKEN")

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != TokenType.ACCESS.value:
        raise UnauthorizedError("Invalid or expired access token.", error_code="INVALID_TOKEN")

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or expired access token.", error_code="INVALID_TOKEN")
    if payload.get("tv") != user.token_version:
        # The password changed (self-service or admin reset) since this
        # token was issued - token_version was bumped, so every token from
        # before that point stops working immediately, not just at its
        # natural expiry or next refresh.
        raise UnauthorizedError(
            "This session is no longer valid. Please sign in again.", error_code="INVALID_TOKEN"
        )

    return user


def require_roles(*roles: RoleName):
    allowed = {role.value for role in roles}

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.name not in allowed:
            raise ForbiddenError("You do not have permission to perform this action.", error_code="ROLE_FORBIDDEN")
        return current_user

    return dependency


def require_permission(code: str):
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        permission_codes = {permission.code for permission in current_user.role.permissions}
        if code not in permission_codes:
            raise ForbiddenError(
                "You do not have permission to perform this action.", error_code="PERMISSION_DENIED"
            )
        return current_user

    return dependency


def require_any_permission(*codes: str):
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        permission_codes = {permission.code for permission in current_user.role.permissions}
        if not permission_codes.intersection(codes):
            raise ForbiddenError(
                "You do not have permission to perform this action.", error_code="PERMISSION_DENIED"
            )
        return current_user

    return dependency
