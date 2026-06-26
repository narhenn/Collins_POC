from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import AuthResponse, UserLogin, UserRegister, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: DB):
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    token = create_access_token(str(user.id), user.email)
    return AuthResponse(
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            created_at=user.created_at,
        ),
        token=token,
    )


@router.post("/login", response_model=AuthResponse)
async def login(data: UserLogin, db: DB):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(str(user.id), user.email)
    return AuthResponse(
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            created_at=user.created_at,
        ),
        token=token,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        created_at=current_user.created_at,
    )
