"""
Точка входа FastAPI-приложения.

Монтирует статику, шаблоны, роутеры.
При старте создаёт таблицы и запускает сидирование.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database.engine import engine
from app.database.models import Base
from app.database.seed import seed_database
from app.database.engine import SessionLocal

# Пути
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создание таблиц и сидирование при старте приложения."""
    Base.metadata.create_all(bind=engine)
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

app.include_router(dashboard.router)
app.include_router(managers.router)
app.include_router(leads.router)
app.include_router(action_items.router)
app.include_router(knowledge.router)
app.include_router(api.router)
