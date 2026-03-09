"""JSON API для JavaScript-компонентов (дерево, календарь, алерты, задачи)."""

from datetime import datetime, date as date_type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import ActionItem, ActionItemStatus, ActionItemPriority, Employee
from app.services.alerts import get_all_alerts
from app.services.calendar_service import get_calendar_events, get_manager_color_legend, _manager_color
from app.services.knowledge_service import get_objection_tree

router = APIRouter(prefix="/api", tags=["api"])


# ── Вспомогательная функция ───────────────────────────────────────────────────

def _ok() -> dict:
    return {"ok": True}

def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}

def _get_task_or_404(task_id: int, db: Session) -> ActionItem:
    task = db.query(ActionItem).get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


# ── Существующие endpoints ────────────────────────────────────────────────────

@router.get("/objections-tree")
def api_objections_tree(db: Session = Depends(get_db)):
    """Полное дерево возражений в виде вложенного JSON."""
    return get_objection_tree(db)


@router.get("/calendar-events")
def api_calendar_events(db: Session = Depends(get_db)):
    """Все события для календаря (отгрузки + задачи)."""
    return get_calendar_events(db)


@router.get("/calendar-events/managers")
def api_calendar_managers(db: Session = Depends(get_db)):
    """Легенда менеджеров с назначенными цветами для отображения на дашборде."""
    return get_manager_color_legend(db)


@router.get("/alerts")
def api_alerts(db: Session = Depends(get_db)):
    """Текущие алерты: просроченные лиды и пропущенные follow-up'ы."""
    return get_all_alerts(db)


@router.get("/employees")
def api_employees(db: Session = Depends(get_db)):
    """Список активных менеджеров с цветами — для дропдаунов в модальных окнах."""
    employees = (
        db.query(Employee)
        .filter(Employee.is_active == True)
        .order_by(Employee.full_name)
        .all()
    )
    return [
        {"id": e.id, "name": e.full_name, "color": _manager_color(e.id)}
        for e in employees
    ]


# ── Task management endpoints ─────────────────────────────────────────────────

class TaskUpdateBody(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: str | None = None   # ISO «YYYY-MM-DD»
    priority: str | None = None


@router.post("/tasks/{task_id}/update")
def api_task_update(task_id: int, body: TaskUpdateBody, db: Session = Depends(get_db)):
    """Изменить поля задачи. Принимает JSON, возвращает {ok: true}."""
    task = _get_task_or_404(task_id, db)
    if body.title is not None:
        task.title = body.title.strip() or task.title
    if body.description is not None:
        task.description = body.description.strip() or None
    if body.due_date:
        try:
            task.due_date = datetime.strptime(body.due_date, "%Y-%m-%d").date()
        except ValueError:
            return _err("Неверный формат даты. Ожидается YYYY-MM-DD")
    if body.priority:
        try:
            task.priority = ActionItemPriority(body.priority)
        except ValueError:
            return _err(f"Неверный приоритет: {body.priority}")
    db.commit()
    return _ok()


@router.post("/tasks/{task_id}/delete")
def api_task_delete(task_id: int, db: Session = Depends(get_db)):
    """Удалить задачу."""
    task = _get_task_or_404(task_id, db)
    db.delete(task)
    db.commit()
    return _ok()


@router.post("/tasks/{task_id}/copy")
def api_task_copy(task_id: int, db: Session = Depends(get_db)):
    """Дублировать задачу (создать новую с теми же данными)."""
    src = _get_task_or_404(task_id, db)
    new_task = ActionItem(
        manager_id=src.manager_id,
        lead_id=src.lead_id,
        co_manager_id=src.co_manager_id,
        title=f"Копия: {src.title}",
        description=src.description,
        status=ActionItemStatus.PENDING,
        priority=src.priority,
        due_date=src.due_date,
    )
    db.add(new_task)
    db.commit()
    return {"ok": True, "new_task_id": new_task.id}


class ManagerIdBody(BaseModel):
    manager_id: int


@router.post("/tasks/{task_id}/transfer")
def api_task_transfer(task_id: int, body: ManagerIdBody, db: Session = Depends(get_db)):
    """Передать задачу другому менеджеру (изменить manager_id)."""
    task = _get_task_or_404(task_id, db)
    emp = db.query(Employee).get(body.manager_id)
    if not emp:
        return _err("Менеджер не найден")
    task.manager_id = body.manager_id
    db.commit()
    return _ok()


@router.post("/tasks/{task_id}/co-assign")
def api_task_co_assign(task_id: int, body: ManagerIdBody, db: Session = Depends(get_db)):
    """Назначить совместного исполнителя (установить co_manager_id)."""
    task = _get_task_or_404(task_id, db)
    if body.manager_id == task.manager_id:
        return _err("Совместный исполнитель не может совпадать с основным")
    emp = db.query(Employee).get(body.manager_id)
    if not emp:
        return _err("Менеджер не найден")
    task.co_manager_id = body.manager_id
    db.commit()
    return _ok()


@router.post("/tasks/{task_id}/co-remove")
def api_task_co_remove(task_id: int, db: Session = Depends(get_db)):
    """Убрать совместного исполнителя."""
    task = _get_task_or_404(task_id, db)
    task.co_manager_id = None
    db.commit()
    return _ok()
