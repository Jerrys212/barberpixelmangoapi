from fastapi import APIRouter

from src.auth.dependencies import CurrentUser
from src.database import SessionDep
from src.users import service as users_service
from src.users.models import User
from src.users.schemas import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(data: UserUpdate, user: CurrentUser, session: SessionDep) -> User:
    return await users_service.update_profile(session, user, data)
