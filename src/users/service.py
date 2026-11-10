from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User
from src.users.repository import UserRepository
from src.users.schemas import UserUpdate


async def update_profile(session: AsyncSession, user: User, data: UserUpdate) -> User:
    values = data.model_dump(exclude_unset=True, exclude_none=True)
    return await UserRepository(session).update(user, values)
