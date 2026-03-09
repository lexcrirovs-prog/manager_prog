"""Роутер для управления CRM-отчётами менеджеров.

Маршруты:
    GET  /reports              — список всех импортированных отчётов + файлы в папке
    POST /reports/scan         — запустить импорт новых файлов из reports/
    GET  /reports/{report_id}  — детали одного отчёта (сделки, суммы)
    POST /reports/{report_id}/delete — удалить отчёт и связанные лиды
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import CrmReport, Lead
from app.services.crm_report_service import scan_reports_directory

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_class=HTMLResponse)
def reports_list(request: Request, db: Session = Depends(get_db)):
    """Страница списка отчётов: импортированные + файлы в папке reports/."""
    from app.main import templates
    from app.config import settings
    from pathlib import Path

    # Уже импортированные отчёты (новые — сверху)
    reports = (
        db.query(CrmReport)
        .order_by(CrmReport.imported_at.desc())
        .all()
    )

    # Файлы в папке, которые ещё не импортированы
    reports_dir = Path(settings.REPORTS_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)
    imported_names = {r.filename for r in reports}
    pending_files = [
        f.name
        for f in sorted(reports_dir.iterdir())
        if f.suffix.lower() in (".csv", ".xlsx", ".xls")
        and not f.name.startswith(".")
        and f.name not in imported_names
    ]

    return templates.TemplateResponse(
        "reports_list.html",
        {
            "request": request,
            "reports": reports,
            "pending_files": pending_files,
            "reports_dir": str(reports_dir.resolve()),
        },
    )


@router.post("/scan")
def scan_reports(request: Request, db: Session = Depends(get_db)):
    """Запускает импорт всех новых файлов из папки reports/."""
    results = scan_reports_directory(db)

    imported = sum(1 for r in results if r["status"] == "ok")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    if not results:
        msg = quote("В папке reports/ нет новых файлов для импорта.")
        return RedirectResponse(f"/reports?msg={msg}&msg_type=warning", status_code=302)

    parts = []
    if imported:
        parts.append(f"импортировано {imported}")
    if errors:
        parts.append(f"ошибок {errors}")
    if skipped:
        parts.append(f"пропущено {skipped}")

    msg_type = "success" if not errors else "warning"
    msg = quote(f"Сканирование завершено: {', '.join(parts)}.")
    return RedirectResponse(f"/reports?msg={msg}&msg_type={msg_type}", status_code=302)


@router.get("/{report_id}", response_class=HTMLResponse)
def report_detail(report_id: int, request: Request, db: Session = Depends(get_db)):
    """Детальная страница отчёта с таблицей сделок."""
    from app.main import templates

    report = db.query(CrmReport).get(report_id)
    if not report:
        return RedirectResponse("/reports", status_code=302)

    leads = (
        db.query(Lead)
        .filter(Lead.crm_report_id == report_id)
        .order_by(Lead.next_step_date)
        .all()
    )

    return templates.TemplateResponse(
        "report_detail.html",
        {
            "request": request,
            "report": report,
            "leads": leads,
        },
    )


@router.post("/{report_id}/delete")
def delete_report(report_id: int, db: Session = Depends(get_db)):
    """Удаляет отчёт и все связанные с ним лиды."""
    report = db.query(CrmReport).get(report_id)
    if report:
        # Лиды каскадно не удалятся автоматически (нет cascade на этой связи),
        # поэтому удаляем явно
        db.query(Lead).filter(Lead.crm_report_id == report_id).delete()
        db.delete(report)
        db.commit()
        msg = quote(f"Отчёт «{report.filename}» удалён вместе со всеми сделками.")
    else:
        msg = quote("Отчёт не найден.")
    return RedirectResponse(f"/reports?msg={msg}&msg_type=success", status_code=302)
