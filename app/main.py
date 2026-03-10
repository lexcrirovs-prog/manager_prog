"""
Точка входа FastAPI-приложения.

Монтирует статику, шаблоны, роутеры.
При старте создаёт таблицы, применяет миграции и запускает сидирование.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.config import settings
from app.database.engine import engine
from app.database.models import Base
from app.database.seed import seed_database
from app.database.engine import SessionLocal

# Пути
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _run_migrations() -> None:
    """Добавляет новые колонки в существующие таблицы (без Alembic).

    Безопасно: каждый ALTER TABLE обёрнут в try/except — если колонка уже
    существует, SQLite бросает OperationalError, мы её игнорируем.
    """
    migrations = [
        # crm_report_id в таблице leads (добавлен в новой версии модели)
        "ALTER TABLE leads ADD COLUMN crm_report_id INTEGER REFERENCES crm_reports(id)",
        # co_manager_id в action_items — совместный исполнитель задачи
        "ALTER TABLE action_items ADD COLUMN co_manager_id INTEGER REFERENCES employees(id)",
        # priority в leads — приоритет сделки (low/medium/high), дефолт low
        "ALTER TABLE leads ADD COLUMN priority VARCHAR(10) DEFAULT 'low'",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # Колонка уже существует — игнорируем


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создание таблиц, миграции и сидирование при старте приложения."""
    # 1. Создать все таблицы (новые, включая crm_reports)
    Base.metadata.create_all(bind=engine)
    # 2. Добавить новые колонки в существующие таблицы
    _run_migrations()
    # 3. Заполнить начальными данными
    with SessionLocal() as db:
        seed_database(db)
    yield


app = FastAPI(
    title=settings.APP_TITLE,
    lifespan=lifespan,
)

# Статика и шаблоны
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Импорт и подключение роутеров
from app.routers import dashboard, managers, leads, action_items, knowledge, api  # noqa: E402
from app.routers import reports  # noqa: E402

app.include_router(dashboard.router)
app.include_router(managers.router)
app.include_router(leads.router)
app.include_router(action_items.router)
app.include_router(knowledge.router)
app.include_router(api.router)
app.include_router(reports.router)
