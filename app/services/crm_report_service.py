"""Сервис импорта CRM-отчётов из папки reports/.

Оркестрирует:
  1. Сканирование директории на новые CSV/Excel-файлы
  2. Извлечение имени менеджера и периода из имени файла
  3. Сопоставление менеджера с записью Employee в БД
  4. Парсинг файла через excel_parser
  5. Применение NLP-парсера к полю «Примечание» → next_step_date
  6. Сохранение CrmReport + Lead-записей в БД

Использование:
    from app.services.crm_report_service import scan_reports_directory
    results = scan_reports_directory(db)
"""

import re
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import CrmReport, Employee, Lead, LeadStatus
from app.services.excel_parser import parse_bytes
from app.services.followup_parser import get_followup_date


# ──────────────────────────────────────────────────────────────
# Извлечение метаданных из имени файла
# ──────────────────────────────────────────────────────────────

def extract_manager_name(filename: str) -> Optional[str]:
    """Извлекает имя/фамилию менеджера из имени файла.

    Поддерживаемые форматы:
      «Отчет CRM 01-28.02.2026(Боев).csv»    → «Боев»
      «report_Иванов_2026.xlsx»               → «Иванов»
      «Боев_отчет_январь.csv»                 → «Боев» (первое слово из кириллицы)
    """
    stem = Path(filename).stem

    # Формат 1: имя в скобках — «(Боев)»
    m = re.search(r"\(([А-ЯЁа-яёA-Za-z][^\)]{1,50})\)", stem)
    if m:
        return m.group(1).strip()

    # Формат 2: имя между подчёркиваниями — «_Иванов_»
    m = re.search(r"(?:^|_)([А-ЯЁа-яё][а-яёА-ЯЁ]{2,30})(?:_|$)", stem)
    if m:
        candidate = m.group(1)
        # Исключаем общие слова типа «отчет», «CRM», «отчёт»
        if candidate.lower() not in ("отчет", "отчёт", "отчетcrm", "crm", "неделя", "январь",
                                     "февраль", "март", "апрель", "май", "июнь", "июль",
                                     "август", "сентябрь", "октябрь", "ноябрь", "декабрь"):
            return candidate

    return None


def extract_report_dates(filename: str) -> tuple[Optional[date], Optional[date]]:
    """Извлекает период отчёта из имени файла.

    Поддерживаемые форматы:
      «01-28.02.2026»      → (01.02.2026, 28.02.2026)  — диапазон дней в одном месяце
      «01.02-28.02.2026»   → (01.02.2026, 28.02.2026)  — полные даты через дефис
      «15.03.2026»         → (15.03.2026, 15.03.2026)  — одиночная дата
    """
    stem = Path(filename).stem

    # «DD-DD.MM.YYYY» — один месяц, разные дни
    m = re.search(r"(\d{1,2})-(\d{1,2})\.(\d{2})\.(\d{4})", stem)
    if m:
        try:
            y, mo = int(m.group(4)), int(m.group(3))
            return date(y, mo, int(m.group(1))), date(y, mo, int(m.group(2)))
        except ValueError:
            pass

    # «DD.MM-DD.MM.YYYY» — диапазон дат
    m = re.search(r"(\d{1,2})\.(\d{2})-(\d{1,2})\.(\d{2})\.(\d{4})", stem)
    if m:
        try:
            y = int(m.group(5))
            return date(y, int(m.group(2)), int(m.group(1))), date(y, int(m.group(4)), int(m.group(3)))
        except ValueError:
            pass

    # «DD.MM.YYYY» — одиночная дата
    m = re.search(r"(\d{1,2})\.(\d{2})\.(\d{4})", stem)
    if m:
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return d, d
        except ValueError:
            pass

    return None, None


def find_manager_by_name(db: Session, name_raw: str) -> Optional[Employee]:
    """Сопоставляет имя из файла с записью Employee (нечёткий поиск по подстроке).

    Например, «Боев» найдёт «Александр Боев».
    """
    if not name_raw:
        return None
    name_lower = name_raw.strip().lower()
    for emp in db.query(Employee).filter(Employee.is_active.is_(True)).all():
        if name_lower in emp.full_name.lower():
            return emp
    return None


# ──────────────────────────────────────────────────────────────
# Основная логика сканирования
# ──────────────────────────────────────────────────────────────

def scan_reports_directory(db: Session) -> list[dict]:
    """Сканирует папку REPORTS_DIR и импортирует все новые файлы.

    Файлы, которые уже есть в таблице crm_reports, пропускаются.

    Returns:
        Список словарей — по одному на каждый обнаруженный файл:
        {filename, status, message, leads_count, total_amount, manager}
    """
    reports_dir = Path(settings.REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Имена уже импортированных файлов
    imported: set[str] = {
        row[0] for row in db.query(CrmReport.filename).all()
    }

    results: list[dict] = []

    for filepath in sorted(reports_dir.iterdir()):
        if filepath.suffix.lower() not in (".csv", ".xlsx", ".xls"):
            continue
        if filepath.name.startswith("."):
            continue

        if filepath.name in imported:
            results.append({
                "filename": filepath.name,
                "status": "skipped",
                "message": "Уже импортирован ранее",
                "leads_count": 0,
                "total_amount": 0.0,
                "manager": None,
            })
            continue

        result = _import_file(db, filepath)
        results.append(result)

    return results


def _import_file(db: Session, filepath: Path) -> dict:
    """Импортирует один файл: парсит → NLP → сохраняет в БД."""
    filename = filepath.name

    manager_name_raw = extract_manager_name(filename)
    date_start, date_end = extract_report_dates(filename)
    manager = find_manager_by_name(db, manager_name_raw) if manager_name_raw else None
    reference_date = date_end or date.today()

    # Создаём запись отчёта (status=processing, обновим в конце)
    report = CrmReport(
        filename=filename,
        manager_id=manager.id if manager else None,
        manager_name_raw=manager_name_raw,
        report_date_start=date_start,
        report_date_end=date_end,
        status="processing",
    )
    db.add(report)
    db.flush()  # получаем report.id до commit

    try:
        content = filepath.read_bytes()
        rows = parse_bytes(content, filename)

        total_amount = 0.0
        leads_saved = 0

        for row in rows:
            customer = row.get("customer")
            if not customer:
                continue

            # Поле «Примечание» может лежать как в notes, так и в next_step
            notes_text: str = row.get("notes") or row.get("next_step") or ""

            # NLP: извлекаем дату следующего шага из примечания
            followup = (
                get_followup_date(
                    notes_text,
                    reference_date,
                    default_days=settings.FOLLOWUP_DEFAULT_DAYS,
                )
                if notes_text.strip()
                else None
            )

            amount = row.get("amount")
            if amount:
                total_amount += float(amount)

            lead = Lead(
                manager_id=manager.id if manager else None,
                crm_report_id=report.id,
                update_date=row.get("update_date") or reference_date,
                status=row.get("status", LeadStatus.NEW),
                customer=customer,
                equipment=row.get("equipment"),
                amount=amount,
                notes=notes_text or None,
                next_step=notes_text[:500] if notes_text else None,
                next_step_date=followup,
                source="crm_report",
                upload_batch_id=str(report.id),
            )
            db.add(lead)
            leads_saved += 1

        report.total_rows = leads_saved
        report.total_amount = total_amount
        report.status = "ok"
        db.commit()

        return {
            "filename": filename,
            "status": "ok",
            "message": f"Импортировано {leads_saved} сделок",
            "leads_count": leads_saved,
            "total_amount": total_amount,
            "manager": manager.full_name if manager else f"Не найден ({manager_name_raw or '?'})",
        }

    except Exception as exc:
        db.rollback()
        # Сохраняем запись об ошибке
        report_err = CrmReport(
            filename=filename,
            manager_id=manager.id if manager else None,
            manager_name_raw=manager_name_raw,
            report_date_start=date_start,
            report_date_end=date_end,
            status="error",
            error_message=str(exc)[:500],
        )
        db.add(report_err)
        db.commit()

        return {
            "filename": filename,
            "status": "error",
            "message": str(exc)[:300],
            "leads_count": 0,
            "total_amount": 0.0,
            "manager": manager.full_name if manager else manager_name_raw,
        }


# ──────────────────────────────────────────────────────────────
# Напоминания (используется CLI и alerts.py)
# ──────────────────────────────────────────────────────────────

def get_due_reminders(db: Session) -> list[dict]:
    """Возвращает список просроченных/подошедших follow-up'ов из CRM-отчётов.

    Отбирает лиды из источника crm_report, у которых next_step_date <= сегодня
    и которые ещё не в финальном статусе (won/lost).
    """
    today = date.today()

    leads = (
        db.query(Lead)
        .filter(
            Lead.source == "crm_report",
            Lead.next_step_date.isnot(None),
            Lead.next_step_date <= today,
            Lead.status.notin_([LeadStatus.WON, LeadStatus.LOST]),
        )
        .order_by(Lead.next_step_date)
        .all()
    )

    reminders = []
    for lead in leads:
        days_ago = (today - lead.next_step_date).days
        manager_name = lead.manager.full_name if lead.manager else "Неизвестный менеджер"
        report_date = lead.next_step_date  # ориентировочная дата

        if days_ago == 0:
            timing = "Сегодня"
        elif days_ago == 1:
            timing = "Вчера"
        else:
            timing = f"{days_ago} дн. назад"

        # Форматируем в стиле, указанном в задании
        msg = (
            f"Напоминание: {manager_name} — "
            f"заказчик «{lead.customer}» "
            f"({timing}, {report_date.strftime('%d.%m.%Y')}). "
        )
        if lead.notes:
            short_notes = lead.notes[:120].rstrip()
            msg += f"Примечание: «{short_notes}{'…' if len(lead.notes) > 120 else ''}». "
        msg += "Пора связаться."

        reminders.append({
            "lead_id": lead.id,
            "manager": manager_name,
            "customer": lead.customer,
            "equipment": lead.equipment,
            "notes": lead.notes,
            "follow_up_date": lead.next_step_date,
            "days_overdue": days_ago,
            "message": msg,
        })

    return reminders
