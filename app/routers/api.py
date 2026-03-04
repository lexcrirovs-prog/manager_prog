"""JSON API для JavaScript-компонентов (дерево, календарь, алерты)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.services.alerts import get_all_alerts
from app.services.calendar_service import get_calendar_events
from app.services.knowledge_service import get_objection_tree

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/objections-tree")
def api_objections_tree(db: Session = Depends(get_db)):
    """Полное дерево возражений в виде вложенного JSON."""
    return get_objection_tree(db)


@router.get("/calendar-events")
def api_calendar_events(db: Session = Depends(get_db)):
    """Даты отгрузок для календаря."""
    return get_calendar_events(db)


@router.get("/alerts")
def api_alerts(db: Session = Depends(get_db)):
    """Текущие алерты: просроченные лиды и пропущенные follow-up'ы."""
    return get_all_alerts(db)
