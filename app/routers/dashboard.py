"""Дашборд руководителя — главная страница."""

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import Employee, Lead, LeadStatus, LeadPriority
from app.services.alerts import get_all_alerts
from app.services.calendar_service import get_upcoming_shipments
from app.services.auth_service import get_current_user

router = APIRouter(tags=["dashboard"])


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Главная страница: алерты + календарь отгрузок."""
    from app.main import templates

    current_user = get_current_user(request, db)
    if current_user is None:
        return RedirectResponse("/login", status_code=302)

    alerts = get_all_alerts(db)
    shipments = get_upcoming_shipments(db)
    employees = db.query(Employee).filter(Employee.is_active == True).all()

    # Статистика по сделкам
    lead_q = db.query(Lead)
    if current_user.system_role != "admin":
        lead_q = lead_q.filter(Lead.manager_id == current_user.id)

    total_leads  = lead_q.count()
    active_leads = lead_q.filter(
        Lead.status.notin_([LeadStatus.WON, LeadStatus.LOST, LeadStatus.REFUSAL])
    ).count()
    won_leads    = lead_q.filter(Lead.status == LeadStatus.WON).count()

    # Объекты в фокусе
    focus_q = db.query(Lead).filter(
        Lead.priority == LeadPriority.FOCUS, Lead.status != LeadStatus.REFUSAL
    )
    if current_user.system_role != "admin":
        focus_q = focus_q.filter(Lead.manager_id == current_user.id)
    focus_leads = focus_q.order_by(Lead.update_date.desc()).limit(8).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current_user": current_user,
        "alerts": alerts,
        "shipments": shipments,
        "employees": employees,
        "total_leads": total_leads,
        "active_leads": active_leads,
        "won_leads": won_leads,
        "focus_leads": focus_leads,
        "today": date.today(),
    })
