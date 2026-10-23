from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import SuccessResponse
from app.schemas.user import UserOut
from app.services import auth_service
from app.services.auth_service import build_user_out
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=SuccessResponse[TokenResponse], summary="Log in with email and password")
async def login(payload: LoginRequest, request: Request, session: AsyncSession = Depends(get_db)):
    result = await auth_service.login(session, payload.email, payload.password, request)
    return SuccessResponse(message="Login successful", data=result)


@router.post("/refresh", response_model=SuccessResponse[AccessTokenResponse], summary="Exchange a refresh token for a new access token")
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_db)):
    access_token = await auth_service.refresh_access_token(session, payload.refresh_token)
    return SuccessResponse(message="Token refreshed", data=AccessTokenResponse(access_token=access_token))


@router.post("/logout", response_model=SuccessResponse[None], summary="Log out the current session")
async def logout(current_user: User = Depends(get_current_user)):
    # JWTs are stateless in V1: logout is a client-side token discard.
    # A refresh-token denylist in Redis can be added here without changing the API shape.
    return SuccessResponse(message="Logged out successfully")


@router.get("/me", response_model=SuccessResponse[UserOut], summary="Get the current authenticated user")
async def me(current_user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)):
    user_out = await build_user_out(session, current_user)
    return SuccessResponse(data=user_out)


@router.post("/forgot-password", response_model=SuccessResponse[None], summary="Request a password reset link")
async def forgot_password(payload: ForgotPasswordRequest, session: AsyncSession = Depends(get_db)):
    await auth_service.request_password_reset(session, payload.email)
    return SuccessResponse(message="If that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=SuccessResponse[None], summary="Reset password using a reset token")
async def reset_password(payload: ResetPasswordRequest, session: AsyncSession = Depends(get_db)):
    await auth_service.reset_password(session, payload.token, payload.new_password)
    return SuccessResponse(message="Password reset successfully")


@router.post("/change-password", response_model=SuccessResponse[None], summary="Change the current user's password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    await auth_service.change_password(session, current_user, payload.current_password, payload.new_password)
    return SuccessResponse(message="Password changed successfully")
