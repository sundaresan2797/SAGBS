from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.dependencies.auth import require_permission
from app.models.enums import ROUTINE_ACTIONS
from app.repositories.audit_log_repository import AuditLogFilters
from app.schemas.audit_log import AuditLogOut
from app.schemas.common import PaginatedData, SuccessResponse
from app.services import audit_log_service

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get(
    "",
    response_model=SuccessResponse[PaginatedData[AuditLogOut]],
    summary="List audit log entries",
    dependencies=[Depends(require_permission("audit:view"))],
)
async def list_audit_logs(
    user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    hide_routine: bool = Query(default=False, description="Leave out check-ins, check-outs, sign-ins and sign-outs"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    filters = AuditLogFilters(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
        exclude_actions=[a.value for a in ROUTINE_ACTIONS] if hide_routine else None,
    )
    result = await audit_log_service.list_audit_logs(session, filters, page, page_size)
    return SuccessResponse(data=result)
