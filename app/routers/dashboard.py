"""Дашборд руководителя — главная страница."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import Employee, Lead, LeadStatus
from app.services.alerts import get_all_alerts
from app.services.calendar_service import get_upcoming_shipments

router = APIRouter(tags=["dashboard"])


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Главная страница: алерты + календарь отгрузок."""
    from app.main import templates

    alerts = get_all_alerts(db)
    shipments = get_upcoming_shipments(db)
    employees = db.query(Employee).filter(Employee.is_active == True).all()

    # Статистика по сделкам
    total_leads = db.query(Lead).count()
    active_leads = db.query(Lead).filter(
        Lead.status.notin_([LeadStatus.WON, LeadStatus.LOST])
    ).count()
    won_leads = db.query(Lead).filter(Lead.status == LeadStatus.WON).count()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "alerts": alerts,
        "shipments": shipments,
        "employees": employees,
        "total_leads": total_leads,
        "active_leads": active_leads,
        "won_leads": won_leads,
        "today": date.today(),
    })
