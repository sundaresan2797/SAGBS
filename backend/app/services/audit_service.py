import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction

logger = logging.getLogger("ems.audit")


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    if request.client:
        return request.client.host
    return None


async def log_action(
    session: AsyncSession,
    *,
    user_id: int | None,
    action: AuditAction,
    entity_type: str | None = None,
    entity_id: int | None = None,
    description: str | None = None,
    request: Request | None = None,
) -> None:
    """Append an audit log entry. Never raises: an audit-log failure must not
    block the business operation it is describing."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action.value,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent") if request else None,
        )
        session.add(entry)
        await session.flush()
    except Exception:
        logger.exception("Failed to write audit log for action=%s", action)
