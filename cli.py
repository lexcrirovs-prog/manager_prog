#!/usr/bin/env python3
"""CLI-утилита для Sales Manager.

Команды:
    python cli.py --reminders          Показать все просроченные follow-up'ы
    python cli.py --import             Импортировать новые файлы из папки reports/
    python cli.py --import --dry-run   Показать, что будет импортировано (без записи в БД)

Примеры:
    python cli.py --reminders
    python cli.py --import
    python cli.py --reminders --import
"""

import argparse
import sys
from pathlib import Path

# Чтобы импорты app.* работали из корня проекта
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database.engine import engine, SessionLocal
from app.database.models import Base


def cmd_reminders(db) -> int:
    """Выводит все просроченные/подошедшие follow-up'ы в консоль.

    Возвращает количество найденных напоминаний.
    """
    from app.services.crm_report_service import get_due_reminders

    reminders = get_due_reminders(db)

    if not reminders:
        print("✓ Нет просроченных follow-up'ов — все контакты актуальны.")
        return 0

    print(f"\n{'═' * 70}")
    print(f"  НАПОМИНАНИЯ О FOLLOW-UP'АХ  ({len(reminders)} шт.)")
    print(f"{'═' * 70}\n")

    for i, r in enumerate(reminders, 1):
        overdue_str = (
            "сегодня" if r["days_overdue"] == 0
            else f"{r['days_overdue']} дн. назад"
        )
        print(f"[{i}] {r['message']}")
        if r.get("equipment"):
            print(f"     Оборудование: {r['equipment']}")
        print(f"     Дата follow-up: {r['follow_up_date'].strftime('%d.%m.%Y')} ({overdue_str})")
        print()

    print(f"{'─' * 70}")
    print(f"Итого: {len(reminders)} напоминаний требуют внимания.\n")
    return len(reminders)


def cmd_import(db, dry_run: bool = False) -> int:
    """Импортирует новые файлы из папки reports/.

    dry_run=True — только показывает что будет импортировано.
    Возвращает количество успешно импортированных файлов.
    """
    from app.config import settings
    from app.services.crm_report_service import (
        extract_manager_name, extract_report_dates, find_manager_by_name,
    )
    from app.database.models import CrmReport

    reports_dir = Path(settings.REPORTS_DIR)
    if not reports_dir.exists():
        print(f"Папка отчётов не найдена: {reports_dir.resolve()}")
        print("Создайте папку и положите туда CSV/Excel-файлы отчётов менеджеров.")
        return 0

    imported_names = {r[0] for r in db.query(CrmReport.filename).all()}
    new_files = [
        f for f in sorted(reports_dir.iterdir())
        if f.suffix.lower() in (".csv", ".xlsx", ".xls")
        and not f.name.startswith(".")
        and f.name not in imported_names
    ]

    if not new_files:
        print(f"В папке {reports_dir.resolve()} нет новых файлов для импорта.")
        return 0

    print(f"\nНайдено новых файлов: {len(new_files)}")
    print(f"{'─' * 60}")

    for f in new_files:
        manager_raw = extract_manager_name(f.name)
        d_start, d_end = extract_report_dates(f.name)
        manager = find_manager_by_name(db, manager_raw) if manager_raw else None

        period_str = ""
        if d_start and d_end:
            period_str = (
                f" [{d_start.strftime('%d.%m')}–{d_end.strftime('%d.%m.%Y')}]"
            )

        manager_str = manager.full_name if manager else f"? ({manager_raw or 'имя не найдено'})"
        print(f"  {f.name}")
        print(f"    Менеджер: {manager_str}{period_str}")

    if dry_run:
        print(f"\n[--dry-run] Импорт не выполнен. Уберите флаг --dry-run для реального импорта.")
        return 0

    # Реальный импорт
    print(f"\nИмпортирую...\n")
    from app.services.crm_report_service import scan_reports_directory

    results = scan_reports_directory(db)
    ok = errors = skipped = 0

    for r in results:
        status_icon = {"ok": "✓", "error": "✗", "skipped": "–"}.get(r["status"], "?")
        print(f"  {status_icon} {r['filename']}")
        if r["status"] == "ok":
            print(f"    → {r['message']} | Менеджер: {r['manager']}")
            if r["total_amount"]:
                print(f"    → Σ КП: {r['total_amount']:,.0f}")
            ok += 1
        elif r["status"] == "error":
            print(f"    ✗ Ошибка: {r['message']}")
            errors += 1
        elif r["status"] == "skipped":
            skipped += 1

    print(f"\n{'─' * 60}")
    parts = []
    if ok:
        parts.append(f"импортировано: {ok}")
    if errors:
        parts.append(f"ошибок: {errors}")
    if skipped:
        parts.append(f"пропущено: {skipped}")
    print(f"Готово. {', '.join(parts)}.\n")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Sales Manager CLI — управление отчётами и напоминаниями",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--reminders",
        action="store_true",
        help="Показать все просроченные follow-up'ы из CRM-отчётов",
    )
    parser.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        help="Импортировать новые файлы из папки reports/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="С --import: только показать файлы, не записывать в БД",
    )

    args = parser.parse_args()

    if not args.reminders and not args.do_import:
        parser.print_help()
        sys.exit(0)

    # Инициализация БД
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        exit_code = 0

        if args.do_import:
            cmd_import(db, dry_run=args.dry_run)

        if args.reminders:
            count = cmd_reminders(db)
            # Ненулевой exit-code если есть напоминания (удобно для cron-скриптов)
            if count > 0:
                exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
