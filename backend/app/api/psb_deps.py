"""Зависимости режима ПСБ: без внешнего ingest, проектов и фоновых сервисов."""
from functools import lru_cache
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.config import get_settings
from app.domains.auth.models import User
from app.domains.auth.security import decode_access_token
from app.domains.auth.service import AuthService
from app.shared.db import get_db
from app.shared.ollama.client import OllamaClient

bearer = HTTPBearer(auto_error=False)

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db, get_settings())

@lru_cache
def get_ollama() -> OllamaClient:
    return OllamaClient(get_settings())

def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds or not creds.credentials:
        raise HTTPException(401, "Необходим вход в аккаунт")
    try:
        user_id = int(decode_access_token(creds.credentials, get_settings())["sub"])
    except Exception:
        raise HTTPException(401, "Сессия истекла. Войдите снова.") from None
    return AuthService(db, get_settings()).get_user(user_id)
