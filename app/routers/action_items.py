"""CRUD-операции для задач и целей."""

from datetime import datetime, date

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import (
    Employee, ActionItem, ActionItemStatus, ActionItemPriority, Lead,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def task_list(
    request: Request,
    manager_id: int = None,
    status: str = None,
    db: Session = Depends(get_db),
):
    """Список задач с фильтрацией."""
    from app.main import templates

    query = db.query(ActionItem)
    if manager_id:
        query = query.filter(ActionItem.manager_id == manager_id)
    if status:
        query = query.filter(ActionItem.status == status)

    tasks = query.order_by(ActionItem.due_date.asc().nullslast()).all()
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    statuses = [s.value for s in ActionItemStatus]
    priorities = [p.value for p in ActionItemPriority]

    # Автоматически помечаем просроченные задачи
    today = date.today()
    for task in tasks:
        if (task.due_date and task.due_date < today
                and task.status not in (ActionItemStatus.COMPLETED, ActionItemStatus.OVERDUE)):
            task.status = ActionItemStatus.OVERDUE
    db.commit()

    return templates.TemplateResponse("action_items.html", {
        "request": request,
        "tasks": tasks,
        "employees": employees,
        "statuses": statuses,
        "priorities": priorities,
        "filter_manager_id": manager_id,
        "filter_status": status,
        "today": today,
    })


@router.post("/new")
async def create_task(
    manager_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("medium"),
    due_date: str = Form(""),
    lead_id: int = Form(None),
    db: Session = Depends(get_db),
):
    """Создание новой задачи."""
    task = ActionItem(
        manager_id=manager_id,
        lead_id=lead_id if lead_id else None,
        title=title,
        description=description or None,
        priority=ActionItemPriority(priority),
        due_date=datetime.strptime(due_date, "%Y-%m-%d").date() if due_date else None,
    )
    db.add(task)
    db.commit()
    return RedirectResponse("/tasks", status_code=302)


@router.post("/{task_id}/update")
async def update_task(
    task_id: int,
    title: str = Form(...),
    description: str = Form(""),
    status: str = Form("pending"),
    priority: str = Form("medium"),
    due_date: str = Form(""),
    db: Session = Depends(get_db),
):
    """Обновление задачи."""
    task = db.query(ActionItem).get(task_id)
    if not task:
        return RedirectResponse("/tasks", status_code=302)

    task.title = title
    task.description = description or None
    task.status = ActionItemStatus(status)
    task.priority = ActionItemPriority(priority)
    task.due_date = datetime.strptime(due_date, "%Y-%m-%d").date() if due_date else None

    if task.status == ActionItemStatus.COMPLETED and not task.completed_at:
        task.completed_at = datetime.now()

    db.commit()
    return RedirectResponse("/tasks", status_code=302)


@router.post("/{task_id}/complete")
async def complete_task(task_id: int, db: Session = Depends(get_db)):
    """Отметить задачу как выполненную."""
    task = db.query(ActionItem).get(task_id)
    if task:
        task.status = ActionItemStatus.COMPLETED
        task.completed_at = datetime.now()
        db.commit()
    return RedirectResponse("/tasks", status_code=302)


@router.post("/{task_id}/delete")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    """Удаление задачи."""
    task = db.query(ActionItem).get(task_id)
    if task:
        db.delete(task)
        db.commit()
    return RedirectResponse("/tasks", status_code=302)
