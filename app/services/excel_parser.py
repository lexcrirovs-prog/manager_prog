"""Парсинг Excel/CSV файлов из CRM-экспорта.

Ожидаемые колонки (русские названия):
    Дата обновления, Статус, Заказчик, Оборудование, Сумма,
    Следующий шаг, Дата следующего шага, Плановая дата отгрузки
"""

import csv
import io
from datetime import datetime, date
from typing import Any

from fastapi import UploadFile

# Маппинг русских колонок → внутренние имена
COLUMN_MAP = {
    "дата обновления": "update_date",
    "статус": "status_raw",
    "заказчик": "customer",
    "оборудование": "equipment",
    "сумма": "amount",
    "следующий шаг": "next_step",
    "дата следующего шага": "next_step_date",
    "плановая дата отгрузки": "planned_shipment_date",
}

# Маппинг русских статусов → enum-значения
STATUS_MAP = {
    "новый": "new",
    "новая": "new",
    "в работе": "in_progress",
    "переговоры": "negotiation",
    "контракт": "contract",
    "договор": "contract",
    "выиграна": "won",
    "выигран": "won",
    "закрыта": "won",
    "проиграна": "lost",
    "проигран": "lost",
    "потеряна": "lost",
    "неактивна": "stale",
    "заморожена": "stale",
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
    text = str(value).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _map_status(raw: str | None) -> str:
    """Преобразует русский статус в enum-значение."""
    if not raw:
        return "new"
    cleaned = raw.strip().lower()
    return STATUS_MAP.get(cleaned, "new")


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
    # Пробуем определить кодировку
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
        # Попробуем с запятой
        reader = csv.DictReader(io.StringIO(text), delimiter=",")

    return _process_rows(reader)


def _parse_xlsx(content: bytes) -> list[dict]:
    """Парсинг Excel-файла (.xlsx)."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # Первая строка — заголовки
    headers = [str(h) if h else "" for h in rows[0]]
    data = []
    for row in rows[1:]:
        row_dict = {}
        for i, val in enumerate(row):
            if i < len(headers):
                row_dict[headers[i]] = val
        data.append(row_dict)

    return _process_rows_from_dicts(data, headers)


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
    """Обрабатывает список словарей из Excel."""
    column_mapping = {}
    for h in headers:
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
