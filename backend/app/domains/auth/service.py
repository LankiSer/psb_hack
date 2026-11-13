from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.domains.auth.models import User
from app.domains.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    def register(self, email: str, password: str) -> tuple[User, str]:
        # 0. Проверка уникальности
        exists = self._db.query(User).filter(User.email == email.lower()).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        # 1. Создание пользователя
        user = User(email=email.lower().strip(), password_hash=hash_password(password))
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)

        # 2. Токен
        token = create_access_token(user_id=user.id, email=user.email, settings=self._settings)
        return user, token

    def login(self, email: str, password: str) -> tuple[User, str]:
        # 0. Поиск
        user = self._db.query(User).filter(User.email == email.lower()).first()
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # 1. Токен
        token = create_access_token(user_id=user.id, email=user.email, settings=self._settings)
        return user, token

    def get_user(self, user_id: int) -> User:
        user = self._db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
