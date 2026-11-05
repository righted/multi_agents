from fastapi import APIRouter, HTTPException, Request

from app.core.auth import create_access_token, get_current_user, hash_password, verify_password
from app.db import user_store
from app.models.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from fastapi import Depends

router = APIRouter()


@router.post("/auth/register", response_model=TokenResponse)
async def register(body: RegisterRequest):
    """注册已关闭，账号由管理员预置"""
    raise HTTPException(status_code=403, detail="暂不开放注册")


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """账号密码登录"""
    user = user_store.get_user_by_username(body.username)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user["id"], user["username"])
    return TokenResponse(access_token=token, user=UserResponse(id=user["id"], username=user["username"], created_at=user["created_at"]))


@router.get("/auth/me", response_model=UserResponse)
async def me(request: Request, user: dict = Depends(get_current_user)):
    """当前登录用户"""
    return UserResponse(**user)
