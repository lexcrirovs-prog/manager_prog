"""CRUD-операции для сделок/лидов."""

import re
from datetime import datetime, date

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import Employee, Lead, LeadStatus, LeadPriority

router = APIRouter(prefix="/leads", tags=["leads"])

# ──────────────────────────────────────────────
# Авто-определение приоритета по примечанию
# ──────────────────────────────────────────────

# Ключевые слова для высокого приоритета: идёт борьба за цену с конкурентами
_HIGH_KEYWORDS = re.compile(
    r"конкурент|конкуренци|ценовая|цена.{0,15}конкурент|конкурент.{0,15}цена"
    r"|дешевле|дороже предлаг|другой поставщик|другие поставщики"
    r"|альтернативн.{0,10}предложени|сравниваю|сравнивают|борьба|торг",
    re.IGNORECASE,
)

# Ключевые слова для среднего приоритета: был конкретный запрос на котёл
_MEDIUM_KEYWORDS = re.compile(
    r"запрос|котел|котёл|запросил|заявка на|нужен котел|нужен котёл"
    r"|прислал запрос|интересует котел|интересует котёл|технические требовани"
    r"|КП|коммерческое предложение|спецификаци",
    re.IGNORECASE,
)


def infer_priority_from_notes(notes: str | None) -> LeadPriority:
    """Определяет приоритет сделки на основе текста примечания.

    HIGH  — есть признаки ценовой конкуренции с конкурентами.
    MEDIUM — был конкретный запрос на котёл/оборудование.
    LOW   — холодный обзвон/рассылка «на будущее» или пустое примечание.
    """
    if not notes or not notes.strip():
        return LeadPriority.LOW
    if _HIGH_KEYWORDS.search(notes):
        return LeadPriority.HIGH
    if _MEDIUM_KEYWORDS.search(notes):
        return LeadPriority.MEDIUM
    return LeadPriority.LOW


# ──────────────────────────────────────────────
# Роуты
# ──────────────────────────────────────────────

@router.get("")
def lead_list(
    request: Request,
    manager_id: int = None,
    status: str = None,
    priority: str = None,
    db: Session = Depends(get_db),
):
    """Список всех сделок с фильтрацией по менеджеру, статусу и приоритету."""
    from app.main import templates

    query = db.query(Lead)
    if manager_id:
        query = query.filter(Lead.manager_id == manager_id)
    if status:
        query = query.filter(Lead.status == status)
    if priority:
        query = query.filter(Lead.priority == priority)

    leads = query.order_by(Lead.update_date.desc()).all()
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    statuses = [s.value for s in LeadStatus]
    priorities = [p.value for p in LeadPriority]

    return templates.TemplateResponse("lead_list.html", {
        "request": request,
        "leads": leads,
        "employees": employees,
        "statuses": statuses,
        "priorities": priorities,
        "filter_manager_id": manager_id,
        "filter_status": status,
        "filter_priority": priority,
        "today": date.today(),
    })


@router.get("/new")
def new_lead_form(request: Request, db: Session = Depends(get_db)):
    """Форма создания новой сделки."""
    from app.main import templates

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    statuses = [s.value for s in LeadStatus]
    priorities = [p.value for p in LeadPriority]

    return templates.TemplateResponse("lead_form.html", {
        "request": request,
        "lead": None,
        "employees": employees,
        "statuses": statuses,
        "priorities": priorities,
    })


@router.post("/new")
async def create_lead(
    manager_id: int = Form(...),
    customer: str = Form(...),
    status: str = Form("new"),
    equipment: str = Form(""),
    amount: float = Form(None),
    next_step: str = Form(""),
    next_step_date: str = Form(""),
    planned_shipment_date: str = Form(""),
    notes: str = Form(""),
    priority: str = Form(""),
    db: Session = Depends(get_db),
):
    """Создание сделки вручную.

    Приоритет определяется автоматически из примечания, если не задан явно.
    По умолчанию — низкий.
    """
    # Если приоритет не передан явно, определяем из примечания
    if priority and priority in [p.value for p in LeadPriority]:
        resolved_priority = LeadPriority(priority)
    else:
        resolved_priority = infer_priority_from_notes(notes)

    lead = Lead(
        manager_id=manager_id,
        customer=customer,
        status=LeadStatus(status),
        equipment=equipment or None,
        amount=amount,
        next_step=next_step or None,
        next_step_date=datetime.strptime(next_step_date, "%Y-%m-%d").date() if next_step_date else None,
        planned_shipment_date=datetime.strptime(planned_shipment_date, "%Y-%m-%d").date() if planned_shipment_date else None,
        update_date=date.today(),
        source="manual",
        notes=notes or None,
        priority=resolved_priority,
    )
    db.add(lead)
    db.commit()
    return RedirectResponse("/leads", status_code=302)


@router.get("/{lead_id}/edit")
def edit_lead_form(lead_id: int, request: Request, db: Session = Depends(get_db)):
    """Форма редактирования сделки."""
    from app.main import templates

    lead = db.query(Lead).get(lead_id)
    if not lead:
        return RedirectResponse("/leads", status_code=302)

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    statuses = [s.value for s in LeadStatus]
    priorities = [p.value for p in LeadPriority]

    return templates.TemplateResponse("lead_form.html", {
        "request": request,
        "lead": lead,
        "employees": employees,
        "statuses": statuses,
        "priorities": priorities,
    })


@router.post("/{lead_id}/edit")
async def update_lead(
    lead_id: int,
    manager_id: int = Form(...),
    customer: str = Form(...),
    status: str = Form("new"),
    equipment: str = Form(""),
    amount: float = Form(None),
    next_step: str = Form(""),
    next_step_date: str = Form(""),
    planned_shipment_date: str = Form(""),
    notes: str = Form(""),
    priority: str = Form(""),
    db: Session = Depends(get_db),
):
    """Обновление сделки.

    Если приоритет задан явно — используется он.
    Если примечание изменилось и приоритет не менялся вручную —
    пересчитывается автоматически из нового примечания.
    """
    lead = db.query(Lead).get(lead_id)
    if not lead:
        return RedirectResponse("/leads", status_code=302)

    lead.manager_id = manager_id
    lead.customer = customer
    lead.status = LeadStatus(status)
    lead.equipment = equipment or None
    lead.amount = amount
    lead.next_step = next_step or None
    lead.next_step_date = datetime.strptime(next_step_date, "%Y-%m-%d").date() if next_step_date else None
    lead.planned_shipment_date = datetime.strptime(planned_shipment_date, "%Y-%m-%d").date() if planned_shipment_date else None
    lead.update_date = date.today()
    lead.notes = notes or None

    if priority and priority in [p.value for p in LeadPriority]:
        lead.priority = LeadPriority(priority)
    else:
        lead.priority = infer_priority_from_notes(notes)

    db.commit()
    return RedirectResponse("/leads", status_code=302)


@router.post("/{lead_id}/delete")
async def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    """Удаление сделки."""
    lead = db.query(Lead).get(lead_id)
    if lead:
        db.delete(lead)
        db.commit()
    return RedirectResponse("/leads", status_code=302)
