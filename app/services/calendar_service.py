"""Сервис календаря отгрузок: выделяет сделки с близкими датами отгрузки."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.database.models import Lead, LeadStatus, Employee


def get_upcoming_shipments(db: Session) -> dict:
    """Сделки с плановой датой отгрузки в ближайшие 7 и 14 дней.

    Returns:
        dict с ключами 'within_7_days' и 'within_14_days'
    """
    today = date.today()
    day_7 = today + timedelta(days=7)
    day_14 = today + timedelta(days=14)

    active_statuses = [LeadStatus.NEW, LeadStatus.IN_PROGRESS, LeadStatus.NEGOTIATION, LeadStatus.CONTRACT]

    leads = (
        db.query(Lead)
        .join(Employee)
        .filter(
            Lead.status.in_(active_statuses),
            Lead.planned_shipment_date != None,
            Lead.planned_shipment_date >= today,
            Lead.planned_shipment_date <= day_14,
        )
        .order_by(Lead.planned_shipment_date.asc())
        .all()
    )

    within_7 = []
    within_14 = []

    for lead in leads:
        item = {
            "lead_id": lead.id,
            "customer": lead.customer,
            "equipment": lead.equipment,
            "manager_name": lead.manager.full_name,
            "manager_id": lead.manager_id,
            "shipment_date": lead.planned_shipment_date.isoformat(),
            "days_until": (lead.planned_shipment_date - today).days,
            "amount": lead.amount,
        }
        if lead.planned_shipment_date <= day_7:
            within_7.append(item)
        else:
            within_14.append(item)

    return {
        "within_7_days": within_7,
        "within_14_days": within_14,
    }


def get_calendar_events(db: Session) -> list[dict]:
    """Все сделки с плановой датой отгрузки для JS-календаря."""
    today = date.today()
    start = today - timedelta(days=30)
    end = today + timedelta(days=90)

    leads = (
        db.query(Lead)
        .join(Employee)
        .filter(
            Lead.planned_shipment_date != None,
            Lead.planned_shipment_date >= start,
            Lead.planned_shipment_date <= end,
        )
        .order_by(Lead.planned_shipment_date.asc())
        .all()
    )

    events = []
    for lead in leads:
        days_until = (lead.planned_shipment_date - today).days

        if lead.status in (LeadStatus.WON,):
            color = "#22c55e"  # зелёный — выиграна
        elif days_until <= 7:
            color = "#ef4444"  # красный — скоро
        elif days_until <= 14:
            color = "#f59e0b"  # оранжевый — внимание
        else:
            color = "#3b82f6"  # синий — норма

        events.append({
            "title": f"{lead.customer}",
            "date": lead.planned_shipment_date.isoformat(),
            "manager": lead.manager.full_name,
            "status": lead.status.value,
            "color": color,
            "lead_id": lead.id,
            "equipment": lead.equipment,
            "amount": lead.amount,
        })

    return events
