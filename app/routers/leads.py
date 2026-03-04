"""CRUD-операции для сделок/лидов."""

from datetime import datetime, date

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import Employee, Lead, LeadStatus

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("")
def lead_list(
    request: Request,
    manager_id: int = None,
    status: str = None,
    db: Session = Depends(get_db),
):
    """Список всех сделок с фильтрацией по менеджеру и статусу."""
    from app.main import templates

    query = db.query(Lead)
    if manager_id:
        query = query.filter(Lead.manager_id == manager_id)
    if status:
        query = query.filter(Lead.status == status)

    leads = query.order_by(Lead.update_date.desc()).all()
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    statuses = [s.value for s in LeadStatus]

    return templates.TemplateResponse("lead_list.html", {
        "request": request,
        "leads": leads,
        "employees": employees,
        "statuses": statuses,
        "filter_manager_id": manager_id,
        "filter_status": status,
        "today": date.today(),
    })


@router.get("/new")
def new_lead_form(request: Request, db: Session = Depends(get_db)):
    """Форма создания новой сделки."""
    from app.main import templates

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    statuses = [s.value for s in LeadStatus]

    return templates.TemplateResponse("lead_form.html", {
        "request": request,
        "lead": None,
        "employees": employees,
        "statuses": statuses,
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
    db: Session = Depends(get_db),
):
    """Создание сделки вручную."""
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

    return templates.TemplateResponse("lead_form.html", {
        "request": request,
        "lead": lead,
        "employees": employees,
        "statuses": statuses,
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
    db: Session = Depends(get_db),
):
    """Обновление сделки."""
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
