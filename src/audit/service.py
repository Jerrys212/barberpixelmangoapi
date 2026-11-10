import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.models import AuditAction, AuditLog
from src.audit.repository import AuditRepository


async def record(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    action: AuditAction,
    target_type: str,
    target_id: uuid.UUID | None,
    ip_address: str | None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        details=details or {},
    )
    return await AuditRepository(session).add(entry)
