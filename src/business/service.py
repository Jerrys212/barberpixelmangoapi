from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import service as audit_service
from src.audit.models import AuditAction
from src.auth.service import ClientInfo
from src.business.models import BusinessProfile
from src.business.repository import BusinessRepository
from src.business.schemas import BusinessUpdate
from src.users.models import User


async def get_profile(session: AsyncSession) -> BusinessProfile:
    return await BusinessRepository(session).get_or_create()


async def lock_calendar(session: AsyncSession) -> BusinessProfile:
    """Serializes every write that changes when the business is open (and, later, bookings)."""
    return await BusinessRepository(session).get_or_create(for_update=True)


async def update_profile(
    session: AsyncSession, owner: User, data: BusinessUpdate, client: ClientInfo
) -> BusinessProfile:
    repo = BusinessRepository(session)
    profile = await repo.get_or_create(for_update=True)
    changes = {
        field: {"old": getattr(profile, field), "new": value}
        for field, value in data.changes().items()
        if getattr(profile, field) != value
    }
    if not changes:
        return profile
    await repo.update(profile, {field: change["new"] for field, change in changes.items()})
    await audit_service.record(
        session,
        actor_user_id=owner.id,
        action=AuditAction.BUSINESS_UPDATED,
        target_type="business_profile",
        target_id=profile.id,
        ip_address=client.ip_address,
        details={"changes": changes},
    )
    return profile
