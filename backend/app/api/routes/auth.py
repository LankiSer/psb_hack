from fastapi import APIRouter, Depends

from app.api.psb_deps import get_auth_service, get_current_user
from app.domains.auth.models import User
from app.domains.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.domains.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    # 0. Регистрация
    _user, token = service.register(body.email, body.password)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    # 0. Логин
    _user, token = service.login(body.email, body.password)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
