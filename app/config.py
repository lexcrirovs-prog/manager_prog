"""Настройки приложения через переменные окружения."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Конфигурация приложения. Значения берутся из env-переменных."""

    DATABASE_URL: str = "sqlite:///./data/sales.db"
    DEBUG: bool = False
    APP_TITLE: str = "Sales Manager — Управление продажами"

    class Config:
        env_file = ".env"


settings = Settings()
