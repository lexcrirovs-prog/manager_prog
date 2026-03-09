"""Парсинг Excel/CSV файлов.

Поддерживает два режима:
1. CRM-экспорт — файл с именованными колонками (Заказчик, Статус, Сумма...)
2. Свободный отчёт — файл без стандартных заголовков (позиционный парсинг)
"""

import csv
import io
from datetime import datetime, date
from typing import Any

from fastapi import UploadFile

from app.database.models import LeadStatus

# Маппинг русских колонок → внутренние имена (CRM-режим)
COLUMN_MAP = {
    "дата обновления": "update_date",
    "дата изменения": "update_date",
    "статус": "status_raw",
    "стадия": "status_raw",
    "этап": "status_raw",
    "заказчик": "customer",
    "клиент": "customer",
    "компания": "customer",
    "контрагент": "customer",
    "организация": "customer",
    "наименование": "customer",
    "название": "customer",
    "оборудование": "equipment",
    "товар": "equipment",
    "продукция": "equipment",
    "номенклатура": "equipment",
    "сумма": "amount",
    "стоимость": "amount",
    "бюджет": "amount",
    "следующий шаг": "next_step",
    "комментарий": "next_step",
    "примечание": "next_step",
    "дата следующего шага": "next_step_date",
    "плановая дата отгрузки": "planned_shipment_date",
    "дата отгрузки": "planned_shipment_date",
}

# Маппинг русских статусов → LeadStatus
STATUS_MAP = {
    "новый": LeadStatus.NEW,
    "новая": LeadStatus.NEW,
    "в работе": LeadStatus.IN_PROGRESS,
    "переговоры": LeadStatus.NEGOTIATION,
    "контракт": LeadStatus.CONTRACT,
    "договор": LeadStatus.CONTRACT,
    "выиграна": LeadStatus.WON,
    "выигран": LeadStatus.WON,
    "закрыта": LeadStatus.WON,
    "проиграна": LeadStatus.LOST,
    "проигран": LeadStatus.LOST,
    "потеряна": LeadStatus.LOST,
    "неактивна": LeadStatus.STALE,
    "заморожена": LeadStatus.STALE,
}


def _normalize_column(name: str) -> str | None:
    """Нормализует название колонки: ищет совпадение по нижнему регистру."""
    cleaned = name.strip().lower()
    for key, value in COLUMN_MAP.items():
        if key in cleaned:
            return value
    return None


def _parse_date(value: Any) -> date | None:
    """Парсинг даты из различных форматов."""
    if isinstance(value, (datetime, date)):
        return value if isinstance(value, date) else value.date()
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: Any) -> float | None:
    """Парсинг суммы: убирает пробелы, запятые и прочий мусор."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _map_status(raw: str | None) -> LeadStatus:
    """Преобразует русский статус в LeadStatus enum."""
    if not raw:
        return LeadStatus.NEW
    cleaned = raw.strip().lower()
    return STATUS_MAP.get(cleaned, LeadStatus.NEW)


async def parse_excel_upload(file: UploadFile) -> list[dict]:
    """Парсит загруженный Excel (.xlsx) или CSV файл, возвращает список словарей для модели Lead."""
    content = await file.read()
    filename = file.filename or ""

    if filename.endswith(".csv"):
        return _parse_csv(content)
    else:
        return _parse_xlsx(content)


def _parse_csv(content: bytes) -> list[dict]:
    """Парсинг CSV-файла."""
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if not reader.fieldnames:
        reader = csv.DictReader(io.StringIO(text), delimiter=",")

    return _process_rows(reader)


def _parse_xlsx(content: bytes) -> list[dict]:
    """Парсинг Excel-файла (.xlsx).

    Сначала пробует найти строку с именованными заголовками (CRM-режим).
    Если заголовки не распознаны — переходит к позиционному парсингу свободного отчёта.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # Ищем первую непустую строку как потенциальные заголовки
    header_row_idx = None
    for i, row in enumerate(rows):
        if any(v is not None and str(v).strip() for v in row):
            header_row_idx = i
            break

    if header_row_idx is None:
        return []

    # Проверяем, есть ли в этой строке известные CRM-заголовки
    potential_headers = [str(h).strip() if h else "" for h in rows[header_row_idx]]
    has_known_headers = any(_normalize_column(h) for h in potential_headers if h)

    if has_known_headers:
        # CRM-режим: строка с заголовками найдена
        data = []
        for row in rows[header_row_idx + 1:]:
            row_dict = {potential_headers[i]: val for i, val in enumerate(row) if i < len(potential_headers)}
            data.append(row_dict)
        return _process_rows_from_dicts(data, potential_headers)
    else:
        # Позиционный режим: свободный отчёт без стандартных заголовков
        return _parse_positional(rows)


def _is_lead_row(row: tuple) -> bool:
    """Проверяет, является ли строка записью о клиенте (не разделителем/заголовком секции)."""
    if not row or len(row) < 2:
        return False

    # Пустая строка
    if all(v is None or not str(v).strip() for v in row):
        return False

    # Колонка 0: должна быть None или число (порядковый номер).
    # Строковое значение в col[0] означает заголовок секции.
    col0 = row[0]
    if col0 is not None and not isinstance(col0, (int, float)):
        col0_str = str(col0).strip()
        if col0_str and not col0_str.isdigit():
            return False

    # Колонка 1 — имя клиента: должна быть непустой строкой
    customer_val = row[1]
    if not customer_val or not str(customer_val).strip():
        return False

    # Строка-разделитель: только колонка 1 непустая, остальные None
    other_non_empty = [
        v for i, v in enumerate(row)
        if i != 1 and v is not None and str(v).strip()
    ]
    if not other_non_empty:
        return False

    return True


def _parse_positional(rows: list[tuple]) -> list[dict]:
    """Позиционный парсинг свободного отчёта менеджера.

    Ожидаемый формат колонок:
        [0] № п/п  [1] Клиент  [2] Оборудование  [3] Описание/Кол-во
        [4] Цена/Кол-во  [5] Комментарий/Следующий шаг  [6] Доп.
    """
    results = []

    for row in rows:
        if not _is_lead_row(row):
            continue

        customer = str(row[1]).strip()

        equipment = str(row[2]).strip() if len(row) > 2 and row[2] else None

        col3 = row[3] if len(row) > 3 else None
        col4 = row[4] if len(row) > 4 else None
        col5 = row[5] if len(row) > 5 else None

        # Сумма: ищем числовое значение в col4, затем в col3
        amount = None
        if isinstance(col4, (int, float)) and not isinstance(col4, bool):
            amount = float(col4)
        elif isinstance(col3, (int, float)) and not isinstance(col3, bool):
            amount = float(col3)

        # Следующий шаг: текстовые значения из col3 и col5
        next_step_parts = []
        if col3 and not isinstance(col3, (int, float, bool)) and str(col3).strip():
            next_step_parts.append(str(col3).strip())
        if col5 and str(col5).strip():
            next_step_parts.append(str(col5).strip())
        next_step = "; ".join(next_step_parts) or None

        results.append({
            "customer": customer,
            "equipment": equipment,
            "amount": amount,
            "next_step": next_step,
            "status": LeadStatus.NEW,
        })

    return results


def _process_rows(reader) -> list[dict]:
    """Обрабатывает строки из csv.DictReader."""
    headers = reader.fieldnames or []
    column_mapping = {}
    for h in headers:
        mapped = _normalize_column(h)
        if mapped:
            column_mapping[h] = mapped

    results = []
    for row in reader:
        lead = _extract_lead(row, column_mapping)
        if lead.get("customer"):
            results.append(lead)

    return results


def _process_rows_from_dicts(data: list[dict], headers: list[str]) -> list[dict]:
    """Обрабатывает список словарей из Excel (CRM-режим)."""
    column_mapping = {}
    for h in headers:
        if h:
            mapped = _normalize_column(h)
            if mapped:
                column_mapping[h] = mapped

    results = []
    for row in data:
        lead = _extract_lead(row, column_mapping)
        if lead.get("customer"):
            results.append(lead)

    return results


def _extract_lead(row: dict, column_mapping: dict) -> dict:
    """Извлекает данные лида из строки."""
    lead = {}
    for original_col, internal_name in column_mapping.items():
        value = row.get(original_col)
        if internal_name == "update_date":
            lead["update_date"] = _parse_date(value)
        elif internal_name == "next_step_date":
            lead["next_step_date"] = _parse_date(value)
        elif internal_name == "planned_shipment_date":
            lead["planned_shipment_date"] = _parse_date(value)
        elif internal_name == "amount":
            lead["amount"] = _parse_amount(value)
        elif internal_name == "status_raw":
            lead["status"] = _map_status(str(value) if value else None)
        elif internal_name == "customer":
            lead["customer"] = str(value).strip() if value else None
        else:
            lead[internal_name] = str(value).strip() if value else None

    return lead
