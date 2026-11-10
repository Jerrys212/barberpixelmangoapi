import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str, *, for_update: bool = False) -> User | None:
        query = select(User).where(User.email == email.lower())
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def lock(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_owner(self) -> User | None:
        result = await self.session.execute(select(User).where(User.role == UserRole.OWNER))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str,
        phone: str,
        role: UserRole,
    ) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            full_name=full_name,
            phone=phone,
            role=role,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User, values: dict[str, Any]) -> User:
        for field, value in values.items():
            setattr(user, field, value)
        await self.session.flush()
        return user
