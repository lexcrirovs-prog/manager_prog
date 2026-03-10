"""Сервис авторизации: хэширование паролей и получение текущего пользователя."""

from passlib.context import CryptContext
from fastapi import Request
from sqlalchemy.orm import Session

from app.database.models import Employee

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def get_current_user(request: Request, db: Session) -> Employee | None:
    """Возвращает текущего залогиненного сотрудника или None."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(Employee, user_id)
