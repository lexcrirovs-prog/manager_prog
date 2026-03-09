"""Сервис извлечения дат follow-up из русскоязычного текста поля "Примечание".

Стратегия (без внешних API):
  1. Regex-фазы: покрывают 90%+ типичных записей менеджеров
  2. dateparser fallback: подхватывает нестандартные формулировки
  3. Дефолт: дата отчёта + FOLLOWUP_DEFAULT_DAYS (если ничего не найдено)

Примеры входных строк и результатов:
  "заказчик взял на подумать 2 недели"     → reference + 14 дней
  "следующие переговоры 25.02"             → 25.02.<текущий год>
  "ждет согласование бюджета до марта"     → 01.03.<текущий год>
  "через месяц созвон"                     → reference + 30 дней
  "позвонить 14.03.2026"                   → 14.03.2026
  "до конца квартала"                      → последний день текущего квартала
  "до 15-го"                               → 15-е текущего или следующего месяца
"""

import re
from datetime import date, timedelta
from typing import Optional

try:
    from dateutil.relativedelta import relativedelta
    _HAS_RELATIVEDELTA = True
except ImportError:
    _HAS_RELATIVEDELTA = False

try:
    import dateparser
    from dateparser.search import search_dates as _dp_search_dates
    _HAS_DATEPARSER = True
except ImportError:
    _HAS_DATEPARSER = False


# ──────────────────────────────────────────────────────────────
# Вспомогательные таблицы
# ──────────────────────────────────────────────────────────────

# Числительные прописью → int
_WORD_TO_NUM: dict[str, int] = {
    "один": 1, "одну": 1, "одного": 1, "одной": 1,
    "два": 2, "две": 2, "двух": 2,
    "три": 3, "трёх": 3, "трех": 3, "трём": 3,
    "четыре": 4, "четырёх": 4, "четырех": 4,
    "пять": 5, "пяти": 5,
    "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7,
    "восемь": 8, "восьми": 8,
    "девять": 9, "девяти": 9,
    "десять": 10, "десяти": 10,
    "полтора": 2,   # приблизительно 1.5 → 2 единицы
    "пару": 2,
    "несколько": 3,
    "неделю": 1,    # «через неделю» = через 1 неделю
    "месяц": 1,     # «через месяц» = через 1 месяц
    "год": 1,
}

# Стемы русских месяцев → номер месяца
_MONTH_STEMS: dict[str, int] = {
    "янв": 1,
    "феврал": 2, "февр": 2,
    "март": 3, "марте": 3, "марта": 3,
    "апрел": 4,
    "май": 5, "мая": 5, "мае": 5,
    "июн": 6,
    "июл": 7,
    "август": 8, "авг": 8,
    "сентябр": 9, "сент": 9,
    "октябр": 10, "окт": 10,
    "ноябр": 11, "нояб": 11,
    "декабр": 12, "дек": 12,
}

# Шаблон числа (цифра или слово)
_NUM_PAT = (
    r"(\d+|один|одну|одного|два|две|двух|три|трёх|трех|четыре|четырёх|"
    r"пять|пяти|шесть|шести|семь|семи|восемь|восьми|девять|девяти|"
    r"десять|полтора|пару|несколько|неделю|месяц|год)"
)

# Шаблоны единиц времени
_DAYS_PAT   = r"(дн[яей]|дней|сутки?|день)"
_WEEKS_PAT  = r"(недел[юьи]|недель|неделя)"
_MONTHS_PAT = r"(месяц[аев]?|месяца)"
_YEARS_PAT  = r"(год[а]?|лет)"
_PERIOD_PAT = rf"(?:{_DAYS_PAT}|{_WEEKS_PAT}|{_MONTHS_PAT}|{_YEARS_PAT})"

# Глаголы паузы: "взял паузу", "взяла на подумать", "отложили"
_PAUSE_VERBS = (
    r"(?:взял[аи]?|взят[ьа]?|отложил[аи]?|рассмотрит|думает|думать|"
    r"подумать|пауза|паузу|подождать|подожд[её]м|ждёт|ждет|ждать|"
    r"рассматривает|на\s+паузе)"
)

# Вводные фразы для следующего контакта
_CONTACT_VERBS = r"(?:переговоры|созвон|звонок|встреча|контакт|связаться|позвонить|написать)"


# ──────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────

def _to_int(s: str) -> int:
    """Преобразует строку с числом или словом в int."""
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    return _WORD_TO_NUM.get(s, 1)


def _add_period(ref: date, n: int, unit: str) -> Optional[date]:
    """Прибавляет n единиц unit к ref. Возвращает None если unit не распознан."""
    u = unit.lower()
    if any(x in u for x in ("дн", "день", "сутк")):
        return ref + timedelta(days=n)
    if any(x in u for x in ("недел",)):
        return ref + timedelta(weeks=n)
    if any(x in u for x in ("месяц",)):
        if _HAS_RELATIVEDELTA:
            return ref + relativedelta(months=n)
        return ref + timedelta(days=30 * n)
    if any(x in u for x in ("год", "лет")):
        if _HAS_RELATIVEDELTA:
            return ref + relativedelta(years=n)
        return ref + timedelta(days=365 * n)
    return None


def _end_of_period(ref: date, period: str) -> date:
    """Возвращает дату конца периода: недели / месяца / квартала / года."""
    p = period.lower()
    if "недел" in p:
        return ref + timedelta(days=6 - ref.weekday())   # воскресенье
    if "месяц" in p:
        if _HAS_RELATIVEDELTA:
            return (ref + relativedelta(months=1)).replace(day=1) - timedelta(days=1)
        return ref.replace(day=28) + timedelta(days=4)   # приближение
    if "кварт" in p:
        quarter_end = {1: 3, 2: 3, 3: 3, 4: 6, 5: 6, 6: 6,
                       7: 9, 8: 9, 9: 9, 10: 12, 11: 12, 12: 12}
        em = quarter_end[ref.month]
        if _HAS_RELATIVEDELTA:
            return date(ref.year, em, 1) + relativedelta(months=1) - timedelta(days=1)
        return date(ref.year, em, 30)
    if "год" in p:
        return date(ref.year, 12, 31)
    return ref + timedelta(days=30)


def _next_occurrence(ref: date, month: int, day: int = 1) -> date:
    """Ближайшая будущая или текущая дата с данным месяцем и днём."""
    try:
        d = date(ref.year, month, day)
    except ValueError:
        d = date(ref.year, month, 1)
    if d < ref:
        try:
            d = date(ref.year + 1, month, day)
        except ValueError:
            d = date(ref.year + 1, month, 1)
    return d


def _find_month_in_text(text: str) -> Optional[int]:
    """Ищет упоминание русского месяца в тексте (по стемам)."""
    tl = text.lower()
    for stem, num in _MONTH_STEMS.items():
        if stem in tl:
            return num
    return None


# ──────────────────────────────────────────────────────────────
# Основная функция
# ──────────────────────────────────────────────────────────────

def parse_followup_date(
    notes: str,
    reference_date: date,
) -> tuple[Optional[date], float]:
    """Извлекает дату follow-up из текста примечания.

    Args:
        notes: Текст поля «Примечание».
        reference_date: Дата отчёта (от неё считаются относительные периоды).

    Returns:
        (follow_up_date, confidence) где confidence ∈ [0.0, 1.0].
        (None, 0.0) если дата не найдена.
    """
    if not notes or not notes.strip():
        return None, 0.0

    text = notes.strip()
    ref = reference_date

    # ── Фаза 1: Явные даты DD.MM.YYYY или DD.MM ────────────────────────────
    for m in re.finditer(r"\b(\d{1,2})\.(\d{2})(?:\.(\d{4}))?\b", text):
        day, month = int(m.group(1)), int(m.group(2))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        year_raw = m.group(3)
        try:
            d = date(int(year_raw), month, day) if year_raw else _next_occurrence(ref, month, day)
            if d >= ref:
                return d, 0.95
        except ValueError:
            continue

    # ── Фаза 2: «через N дней / недель / месяц / год» ─────────────────────
    m = re.search(rf"через\s+{_NUM_PAT}\s+{_PERIOD_PAT}", text, re.IGNORECASE)
    if m:
        n = _to_int(m.group(1))
        unit = next(g for g in m.groups()[1:] if g)
        d = _add_period(ref, n, unit)
        if d:
            return d, 0.90

    # ── Фаза 3: «через неделю / месяц» без числа ──────────────────────────
    m = re.search(r"через\s+(неделю|месяц|год)\b", text, re.IGNORECASE)
    if m:
        unit = m.group(1).lower()
        d = _add_period(ref, 1, unit)
        if d:
            return d, 0.88

    # ── Фаза 4: «взял/отложил/ждёт на N дней/недель» ─────────────────────
    m = re.search(
        rf"{_PAUSE_VERBS}\s+(?:на\s+)?{_NUM_PAT}\s+{_PERIOD_PAT}",
        text, re.IGNORECASE,
    )
    if m:
        groups = m.groups()
        # Первый совпавший digit-or-word
        num_str = next((g for g in groups if g and (g.isdigit() or g.lower() in _WORD_TO_NUM)), None)
        unit_str = next((g for g in groups if g and any(
            x in g.lower() for x in ("дн", "день", "недел", "месяц", "лет", "год", "сутк")
        )), None)
        if num_str and unit_str:
            d = _add_period(ref, _to_int(num_str), unit_str)
            if d:
                return d, 0.85

    # ── Фаза 5: «на N недель/дней» без глагола паузы ─────────────────────
    m = re.search(rf"\bна\s+{_NUM_PAT}\s+{_PERIOD_PAT}\b", text, re.IGNORECASE)
    if m:
        groups = m.groups()
        num_str = next((g for g in groups if g and (g.isdigit() or g.lower() in _WORD_TO_NUM)), None)
        unit_str = next((g for g in groups if g and any(
            x in g.lower() for x in ("дн", "день", "недел", "месяц", "лет", "год")
        )), None)
        if num_str and unit_str:
            d = _add_period(ref, _to_int(num_str), unit_str)
            if d:
                return d, 0.80

    # ── Фаза 6: «до конца [недели / месяца / квартала / года]» ───────────
    m = re.search(r"до\s+конца\s+(\w+)", text, re.IGNORECASE)
    if m:
        return _end_of_period(ref, m.group(1)), 0.75

    # ── Фаза 7: «до N-го» (конкретный день месяца) ───────────────────────
    m = re.search(r"до\s+(\d{1,2})[-\s]?го\b", text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            try:
                d = ref.replace(day=day)
                if d < ref:
                    if _HAS_RELATIVEDELTA:
                        d = (ref + relativedelta(months=1)).replace(day=day)
                    else:
                        d = (ref.replace(day=28) + timedelta(days=4)).replace(day=day)
                return d, 0.75
            except ValueError:
                pass

    # ── Фаза 8: «следующие переговоры/созвон ДД.ММ» ──────────────────────
    m = re.search(
        rf"{_CONTACT_VERBS}\s+(\d{{1,2}})\.(\d{{2}})(?:\.(\d{{4}}))?",
        text, re.IGNORECASE,
    )
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year_raw = m.group(3)
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                d = (
                    date(int(year_raw), month, day)
                    if year_raw
                    else _next_occurrence(ref, month, day)
                )
                if d >= ref:
                    return d, 0.90
            except ValueError:
                pass

    # ── Фаза 9: В начале / середине / конце месяца ────────────────────────
    m = re.search(
        r"в\s+(начале|середине|конце)\s+(?:следующего\s+)?месяца",
        text, re.IGNORECASE,
    )
    if m:
        where = m.group(1).lower()
        if "конц" in where:
            return _end_of_period(ref, "месяца"), 0.70
        elif "середин" in where:
            if _HAS_RELATIVEDELTA:
                base = ref + relativedelta(months=1) if ref.day >= 15 else ref
                return base.replace(day=15), 0.70
            return ref + timedelta(days=15), 0.65
        else:  # начале
            if _HAS_RELATIVEDELTA:
                return (ref + relativedelta(months=1)).replace(day=5), 0.70
            return ref + timedelta(days=30), 0.60

    # ── Фаза 10: Упоминание месяца («в марте», «до апреля», «к февралю») ─
    m = re.search(
        r"(?:в(?:\s+начале|\s+середине|\s+конце)?|до|к|на)\s+([а-яёА-ЯЁ]{3,12})\b",
        text, re.IGNORECASE,
    )
    if m:
        month_num = _find_month_in_text(m.group(1))
        if month_num:
            ctx = m.group(0).lower()
            day = 25 if "конц" in ctx else 15 if "середин" in ctx else 1
            return _next_occurrence(ref, month_num, day), 0.68

    # ── Фаза 11: «ждёт согласования / бюджет / ответ» → +30 дней ─────────
    if re.search(
        r"\b(?:ждёт|ждет|ожидает|ждём|ждем)\s+(?:согласован\w+|бюджет\w*|решени\w+|ответ\w*|одобрени\w+)",
        text, re.IGNORECASE,
    ):
        return ref + timedelta(days=30), 0.55

    # ── Фаза 12: Идиомы «скоро», «на следующей неделе» → +7 дней ─────────
    if re.search(r"\b(?:скоро|на следующей неделе|в ближайшее время)\b", text, re.IGNORECASE):
        return ref + timedelta(days=7), 0.50

    # ── Фаза 13: dateparser (fallback для нестандартных форм) ─────────────
    if _HAS_DATEPARSER:
        try:
            results = _dp_search_dates(
                text,
                languages=["ru"],
                settings={
                    "PREFER_DATES_FROM": "future",
                    "RELATIVE_BASE": reference_date,
                    "RETURN_AS_TIMEZONE_AWARE": False,
                    "PREFER_DAY_OF_MONTH": "first",
                },
            )
            if results:
                for _, dt in results:
                    d = dt.date() if hasattr(dt, "date") else dt
                    if d >= ref:
                        return d, 0.58
        except Exception:
            pass

    return None, 0.0


def get_followup_date(
    notes: str,
    reference_date: date,
    default_days: int = 14,
) -> date:
    """Возвращает дату follow-up или reference_date + default_days если ничего не найдено."""
    d, _ = parse_followup_date(notes, reference_date)
    return d if d is not None else reference_date + timedelta(days=default_days)
