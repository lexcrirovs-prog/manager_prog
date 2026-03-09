"""Сервис календаря: отгрузки и follow-up события из поля «Примечание»."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.database.models import Lead, LeadStatus, Employee

# Палитра цветов для менеджеров (контрастная, хорошо читается на светлой и тёмной теме)
_MANAGER_PALETTE = [
    "#2563eb",  # синий
    "#16a34a",  # зелёный
    "#dc2626",  # красный
    "#d97706",  # янтарный
    "#7c3aed",  # фиолетовый
    "#0891b2",  # голубой
    "#be185d",  # малиновый
    "#059669",  # изумрудный
    "#ea580c",  # оранжевый
    "#0f766e",  # бирюзовый
]


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


def get_followup_calendar_events(db: Session) -> dict:
    """Follow-up события из поля «Примечание» для интерактивного календаря.

    Returns dict:
        {
          "events":   [...],   # список событий
          "managers": [...]    # менеджеры с цветами для фильтра
        }
    """
    # Берём лиды с next_step_date в не-финальных статусах
    leads = (
        db.query(Lead)
        .join(Employee)
        .filter(
            Lead.next_step_date.isnot(None),
            Lead.status.notin_([LeadStatus.WON, LeadStatus.LOST]),
        )
        .order_by(Lead.next_step_date.asc())
        .all()
    )

    # Назначаем каждому менеджеру свой цвет (детерминировано по id)
    manager_ids_ordered: list[int] = []
    seen: set[int] = set()
    for lead in leads:
        mid = lead.manager_id
        if mid and mid not in seen:
            manager_ids_ordered.append(mid)
            seen.add(mid)

    manager_color: dict[int, str] = {
        mid: _MANAGER_PALETTE[i % len(_MANAGER_PALETTE)]
        for i, mid in enumerate(manager_ids_ordered)
    }

    events = []
    for lead in leads:
        color = manager_color.get(lead.manager_id, "#6b7280")
        events.append({
            "id": lead.id,
            "date": lead.next_step_date.isoformat(),
            "customer": lead.customer,
            "manager": lead.manager.full_name if lead.manager else "—",
            "manager_id": lead.manager_id,
            "equipment": lead.equipment,
            "amount": lead.amount,
            "update_date": lead.update_date.isoformat() if lead.update_date else None,
            "notes": lead.notes or lead.next_step,
            "color": color,
        })

    # Список менеджеров для фильтра (только те, у кого есть события)
    manager_rows = (
        db.query(Employee)
        .filter(Employee.id.in_(list(seen)))
        .order_by(Employee.full_name)
        .all()
    )
    managers = [
        {
            "id": emp.id,
            "name": emp.full_name,
            "color": manager_color.get(emp.id, "#6b7280"),
        }
        for emp in manager_rows
    ]

    return {"events": events, "managers": managers}
