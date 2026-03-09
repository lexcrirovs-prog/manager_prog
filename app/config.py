"""Настройки приложения через переменные окружения."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Конфигурация приложения. Значения берутся из env-переменных."""

    DATABASE_URL: str = "sqlite:///./data/sales.db"
    DEBUG: bool = False
    APP_TITLE: str = "Sales Manager — Управление продажами"

    # Папка для входящих CRM-отчётов от менеджеров
    REPORTS_DIR: str = "./reports"

    # Дней до напоминания по follow-up по умолчанию (если NLP не нашёл дату)
    FOLLOWUP_DEFAULT_DAYS: int = 14

    class Config:
        env_file = ".env"


settings = Settings()
