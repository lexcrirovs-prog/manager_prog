"""Парсинг транскриптов совещаний (.txt, .md).

Извлекает контент файла и пытается определить дату совещания
из имени файла или первых строк текста.
"""

import re
from datetime import datetime, date

from fastapi import UploadFile


async def parse_transcript(file: UploadFile) -> dict:
    """Читает файл транскрипта и возвращает его содержимое с метаданными."""
    content_bytes = await file.read()
    filename = file.filename or "transcript.txt"

    # Определяем кодировку
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            content = content_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = content_bytes.decode("utf-8", errors="replace")

    meeting_date = _extract_date_from_filename(filename) or _extract_date_from_content(content)

    return {
        "filename": filename,
        "content": content,
        "meeting_date": meeting_date,
    }


def _extract_date_from_filename(filename: str) -> date | None:
    """Пытается извлечь дату из имени файла (DD.MM.YYYY или YYYY-MM-DD)."""
    patterns = [
        (r"(\d{2})\.(\d{2})\.(\d{4})", "%d.%m.%Y"),
        (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
        (r"(\d{2})-(\d{2})-(\d{4})", "%d-%m-%Y"),
    ]
    for pattern, fmt in patterns:
        match = re.search(pattern, filename)
        if match:
            try:
                return datetime.strptime(match.group(), fmt).date()
            except ValueError:
                continue
    return None


def _extract_date_from_content(content: str) -> date | None:
    """Пытается найти дату в первых 5 строках транскрипта."""
    lines = content.strip().split("\n")[:5]
    for line in lines:
        d = _extract_date_from_filename(line)
        if d:
            return d
    return None


def extract_insights_from_transcript(content: str) -> list[dict]:
    """Полуавтоматическое извлечение инсайтов из транскрипта.

    Ищет ключевые маркеры в тексте и предлагает фрагменты для добавления
    в базу знаний. Возвращает список кандидатов.
    """
    markers = [
        # (тип, ключевые слова для поиска)
        ("objection", ["возражение", "возражают", "клиент говорит", "клиент считает", "не устраивает"]),
        ("technical", ["технически", "характеристик", "параметр", "мощность", "давление", "температур"]),
        ("insight", ["важно", "обратите внимание", "инсайт", "вывод", "ключевой момент"]),
    ]

    results = []
    lines = content.split("\n")

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if not line_lower:
            continue

        for insight_type, keywords in markers:
            if any(kw in line_lower for kw in keywords):
                # Берём контекст: текущую строку + 2 следующих
                context_lines = lines[i:i + 3]
                context = "\n".join(l.strip() for l in context_lines if l.strip())

                results.append({
                    "type": insight_type,
                    "title": line.strip()[:100],
                    "content": context,
                    "line_number": i + 1,
                })
                break

    return results
