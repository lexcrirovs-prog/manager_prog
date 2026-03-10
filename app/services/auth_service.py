"""Сервис авторизации: хэширование паролей и получение текущего пользователя."""

import bcrypt
from fastapi import Request
from sqlalchemy.orm import Session

from app.database.models import Employee


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_current_user(request: Request, db: Session) -> Employee | None:
    """Возвращает текущего залогиненного сотрудника или None."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(Employee, user_id)
