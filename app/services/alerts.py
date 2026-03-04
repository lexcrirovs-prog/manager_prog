"""Логика алертов: обнаружение просроченных лидов и пропущенных follow-up'ов."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.database.models import Lead, LeadStatus, Employee


def get_stale_leads(db: Session, days_threshold: int = 14) -> list[dict]:
    """Сделки без обновлений дольше порогового значения (по умолчанию 14 дней).

    Возвращает лиды в активных статусах, где update_date старше threshold.
    """
    cutoff = date.today() - timedelta(days=days_threshold)
    active_statuses = [LeadStatus.NEW, LeadStatus.IN_PROGRESS, LeadStatus.NEGOTIATION, LeadStatus.CONTRACT]

    leads = (
        db.query(Lead)
        .join(Employee)
        .filter(
            Lead.status.in_(active_statuses),
            Lead.update_date != None,
            Lead.update_date < cutoff,
        )
        .all()
    )

    results = []
    for lead in leads:
        days_since = (date.today() - lead.update_date).days
        results.append({
            "lead_id": lead.id,
            "customer": lead.customer,
            "manager_name": lead.manager.full_name,
            "manager_id": lead.manager_id,
            "last_update": lead.update_date.isoformat(),
            "days_since_update": days_since,
            "status": lead.status.value,
            "message": f"Спросить {lead.manager.full_name} про лид «{lead.customer}» (последний контакт {days_since} дн. назад)",
        })

    return results


def get_missed_followups(db: Session) -> list[dict]:
    """Сделки с просроченной датой следующего шага.

    Если next_step_date < сегодня и статус активный — это пропущенный follow-up.
    """
    today = date.today()
    active_statuses = [LeadStatus.NEW, LeadStatus.IN_PROGRESS, LeadStatus.NEGOTIATION, LeadStatus.CONTRACT]

    leads = (
        db.query(Lead)
        .join(Employee)
        .filter(
            Lead.status.in_(active_statuses),
            Lead.next_step_date != None,
            Lead.next_step_date < today,
        )
        .all()
    )

    results = []
    for lead in leads:
        days_overdue = (today - lead.next_step_date).days
        results.append({
            "lead_id": lead.id,
            "customer": lead.customer,
            "manager_name": lead.manager.full_name,
            "manager_id": lead.manager_id,
            "next_step": lead.next_step,
            "next_step_date": lead.next_step_date.isoformat(),
            "days_overdue": days_overdue,
            "message": f"{lead.manager.full_name}: «{lead.next_step or 'Следующий шаг'}» по «{lead.customer}» просрочен на {days_overdue} дн.",
        })

    return results


def get_all_alerts(db: Session) -> dict:
    """Собирает все алерты в единый словарь."""
    stale = get_stale_leads(db)
    missed = get_missed_followups(db)
    return {
        "stale_leads": stale,
        "missed_followups": missed,
        "total_count": len(stale) + len(missed),
    }
