"""Профили менеджеров: список, детали, загрузка файлов, запись продаж."""

import uuid
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import (
    Employee, Lead, ActionItem, ActionItemStatus, ActionItemPriority,
    Transcript, Sale, LeadStatus, LeadPriority,
)
from app.services.excel_parser import parse_excel_upload
from app.services.transcript_parser import parse_transcript
from app.services.followup_parser import parse_followup_date
from app.services.priority_parser import detect_lead_priority

# Срок follow-up по умолчанию (если дата не найдена в примечании)
_DEFAULT_FOLLOWUP_WEEKS = 2

router = APIRouter(prefix="/managers", tags=["managers"])


@router.get("")
def manager_list(request: Request, db: Session = Depends(get_db)):
    """Список всех менеджеров с базовой статистикой."""
    from app.main import templates

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    stats = {}
    for emp in employees:
        leads_count = db.query(Lead).filter(Lead.manager_id == emp.id).count()
        active_count = db.query(Lead).filter(
            Lead.manager_id == emp.id,
            Lead.status.notin_([LeadStatus.WON, LeadStatus.LOST]),
        ).count()
        sales_count = db.query(Sale).filter(Sale.manager_id == emp.id).count()
        stats[emp.id] = {
            "leads": leads_count,
            "active": active_count,
            "sales": sales_count,
        }

    return templates.TemplateResponse("manager_list.html", {
        "request": request,
        "employees": employees,
        "stats": stats,
    })


@router.get("/{manager_id}")
def manager_detail(manager_id: int, request: Request, db: Session = Depends(get_db)):
    """Детальная страница менеджера: лиды, задачи, транскрипты, продажи."""
    from app.main import templates

    employee = db.query(Employee).get(manager_id)
    if not employee:
        return RedirectResponse("/managers", status_code=302)

    leads = db.query(Lead).filter(Lead.manager_id == manager_id).order_by(Lead.update_date.desc()).all()
    action_items = db.query(ActionItem).filter(ActionItem.manager_id == manager_id).order_by(ActionItem.due_date.asc()).all()
    transcripts = db.query(Transcript).filter(Transcript.manager_id == manager_id).order_by(Transcript.created_at.desc()).all()
    sales = db.query(Sale).filter(Sale.manager_id == manager_id).order_by(Sale.sale_date.desc()).all()

    return templates.TemplateResponse("manager_detail.html", {
        "request": request,
        "employee": employee,
        "leads": leads,
        "action_items": action_items,
        "transcripts": transcripts,
        "sales": sales,
        "today": date.today(),
    })


@router.get("/{manager_id}/upload")
def upload_form(manager_id: int, request: Request, db: Session = Depends(get_db)):
    """Форма загрузки Excel/CSV и транскриптов."""
    from app.main import templates

    employee = db.query(Employee).get(manager_id)
    if not employee:
        return RedirectResponse("/managers", status_code=302)

    return templates.TemplateResponse("manager_upload.html", {
        "request": request,
        "employee": employee,
    })


@router.post("/{manager_id}/upload-excel")
async def upload_excel(
    manager_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Загрузка и парсинг Excel/CSV файла из CRM."""
    employee = db.query(Employee).get(manager_id)
    if not employee:
        return RedirectResponse("/managers", status_code=302)

    redirect_base = f"/managers/{manager_id}"

    filename = file.filename or "файл"
    try:
        batch_id = str(uuid.uuid4())[:8]
        leads_data = await parse_excel_upload(file)
    except Exception as exc:
        exc_str = str(exc).lower()
        if any(k in exc_str for k in ("zipfile", "badzip", "not a zip", "openpyxl", "bad magic")):
            friendly = "файл повреждён или имеет неверный формат (.xlsx/.xls)"
        elif any(k in exc_str for k in ("unicode", "codec", "encoding", "decode")):
            friendly = "ошибка кодировки — сохраните файл в UTF-8 или Windows-1251"
        elif "permission" in exc_str:
            friendly = "нет прав доступа к файлу"
        else:
            friendly = "неверный формат файла или отсутствуют обязательные колонки"
        msg = quote(f"Ошибка загрузки «{filename}»: {friendly}")
        return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=error", status_code=302)

    if not leads_data:
        msg = quote(
            f"Файл «{filename}» обработан, но ни одной сделки не найдено. "
            "Убедитесь, что в файле есть данные о клиентах."
        )
        return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=warning", status_code=302)

    ref_date = date.today()
    try:
        for row in leads_data:
            # «Примечание» может лежать в notes или next_step
            notes_text: str = row.get("notes") or row.get("next_step") or ""

            # NLP-парсер: извлекаем follow-up дату и уверенность из «Примечания»
            followup_date, confidence = parse_followup_date(notes_text, ref_date)
            # Если в отчёте уже указана явная дата — приоритет за ней
            if row.get("next_step_date"):
                followup_date = row["next_step_date"]
                confidence = 1.0

            # Определяем дату задачи: из примечания или дефолт +2 недели
            task_date = followup_date if confidence > 0.0 else (ref_date + timedelta(weeks=_DEFAULT_FOLLOWUP_WEEKS))
            if confidence > 0.0:
                date_comment = "Дата извлечена из примечания к сделке."
            else:
                date_comment = f"Дата в примечании не указана — назначено через {_DEFAULT_FOLLOWUP_WEEKS} недели."

            customer_name = row.get("customer", "Неизвестный")
            # Автоопределение приоритета по тексту примечания
            lead_priority = detect_lead_priority(notes_text)

            lead = Lead(
                manager_id=manager_id,
                update_date=row.get("update_date"),
                status=row.get("status", LeadStatus.NEW),
                priority=lead_priority,
                customer=customer_name,
                equipment=row.get("equipment"),
                amount=row.get("amount"),
                notes=notes_text or None,
                next_step=row.get("next_step") or (notes_text[:500] if notes_text else None),
                next_step_date=task_date,
                planned_shipment_date=row.get("planned_shipment_date"),
                source="upload",
                upload_batch_id=batch_id,
            )
            db.add(lead)
            # flush() нужен, чтобы получить lead.id до создания ActionItem
            db.flush()

            # ── Одна задача на сделку ────────────────────────────────────────
            # Дата = из примечания (если найдена) ИЛИ ref_date + 2 недели.
            db.add(ActionItem(
                manager_id=manager_id,
                lead_id=lead.id,
                title=f"Follow-up: {customer_name}",
                description=f"Автоматическая задача из отчёта. {date_comment}",
                status=ActionItemStatus.PENDING,
                priority=ActionItemPriority.MEDIUM,
                due_date=task_date,
            ))

        db.commit()
    except Exception as exc:
        db.rollback()
        msg = quote(f"Ошибка при сохранении данных из «{filename}»: {str(exc)[:200]}")
        return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=error", status_code=302)

    count = len(leads_data)
    msg = quote(
        f"Успешно загружено {count} событий из файла «{file.filename}» "
        f"для менеджера {employee.full_name}."
    )
    return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=success", status_code=302)


@router.post("/{manager_id}/upload-transcript")
async def upload_transcript(
    manager_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Загрузка транскрипта совещания (.txt/.md)."""
    employee = db.query(Employee).get(manager_id)
    if not employee:
        return RedirectResponse("/managers", status_code=302)

    redirect_base = f"/managers/{manager_id}"

    try:
        parsed = await parse_transcript(file)
        transcript = Transcript(
            manager_id=manager_id,
            filename=parsed["filename"],
            content=parsed["content"],
            meeting_date=parsed.get("meeting_date"),
        )
        db.add(transcript)
        db.commit()
    except Exception as exc:
        db.rollback()
        msg = quote(f"Ошибка при загрузке транскрипта: {str(exc)[:200]}")
        return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=error", status_code=302)

    msg = quote(f"Транскрипт «{file.filename}» успешно загружен.")
    return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=success", status_code=302)


@router.get("/{manager_id}/record-sale")
def sale_form(manager_id: int, request: Request, db: Session = Depends(get_db)):
    """Форма фиксации продажи."""
    from app.main import templates

    employee = db.query(Employee).get(manager_id)
    if not employee:
        return RedirectResponse("/managers", status_code=302)

    leads = db.query(Lead).filter(
        Lead.manager_id == manager_id,
        Lead.status.notin_([LeadStatus.WON, LeadStatus.LOST]),
    ).all()

    return templates.TemplateResponse("sale_record.html", {
        "request": request,
        "employee": employee,
        "leads": leads,
    })


@router.post("/{manager_id}/record-sale")
async def record_sale(
    manager_id: int,
    customer: str = Form(...),
    equipment: str = Form(""),
    serial_numbers: str = Form(""),
    amount: float = Form(...),
    discount: float = Form(0),
    shipment_date: str = Form(""),
    sale_date: str = Form(...),
    lead_id: int = Form(None),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    """Сохранение записи о продаже."""
    from datetime import datetime

    sale = Sale(
        manager_id=manager_id,
        lead_id=lead_id if lead_id else None,
        customer=customer,
        equipment=equipment or None,
        serial_numbers=serial_numbers or None,
        amount=amount,
        discount=discount or None,
        shipment_date=datetime.strptime(shipment_date, "%Y-%m-%d").date() if shipment_date else None,
        sale_date=datetime.strptime(sale_date, "%Y-%m-%d").date(),
        notes=notes or None,
    )
    db.add(sale)

    # Если привязана сделка — обновляем её статус на WON
    if lead_id:
        lead = db.query(Lead).get(lead_id)
        if lead:
            lead.status = LeadStatus.WON

    db.commit()
    return RedirectResponse(f"/managers/{manager_id}", status_code=302)
