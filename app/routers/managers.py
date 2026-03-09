"""Профили менеджеров: список, детали, загрузка файлов, запись продаж."""

import uuid
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import (
    Employee, Lead, ActionItem, Transcript, Sale, LeadStatus,
)
from app.services.excel_parser import parse_excel_upload
from app.services.transcript_parser import parse_transcript

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

    try:
        batch_id = str(uuid.uuid4())[:8]
        leads_data = await parse_excel_upload(file)
    except Exception as exc:
        msg = quote(f"Ошибка при чтении файла: {str(exc)[:200]}")
        return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=error", status_code=302)

    if not leads_data:
        msg = quote(
            "Файл обработан, но ни одной сделки не найдено. "
            "Убедитесь, что в файле есть данные о клиентах."
        )
        return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=warning", status_code=302)

    try:
        for row in leads_data:
            lead = Lead(
                manager_id=manager_id,
                update_date=row.get("update_date"),
                status=row.get("status", LeadStatus.NEW),
                customer=row.get("customer", "Неизвестный"),
                equipment=row.get("equipment"),
                amount=row.get("amount"),
                next_step=row.get("next_step"),
                next_step_date=row.get("next_step_date"),
                planned_shipment_date=row.get("planned_shipment_date"),
                source="upload",
                upload_batch_id=batch_id,
            )
            db.add(lead)
        db.commit()
    except Exception as exc:
        db.rollback()
        msg = quote(f"Ошибка при сохранении данных: {str(exc)[:200]}")
        return RedirectResponse(f"{redirect_base}?msg={msg}&msg_type=error", status_code=302)

    count = len(leads_data)
    msg = quote(f"Успешно загружено {count} сделок из файла «{file.filename}».")
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
