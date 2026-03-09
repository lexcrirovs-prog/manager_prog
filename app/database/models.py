"""
ORM-модели базы данных для системы управления совещаниями отдела продаж.

Таблицы:
    - employees: Сотрудники (менеджеры, руководство)
    - crm_reports: Загруженные CRM-отчёты (один файл — одна запись)
    - leads: Сделки/Лиды из CRM-отчётов
    - action_items: Задачи и цели с дедлайнами
    - transcripts: Транскрипты совещаний
    - sales: Зафиксированные продажи
    - objections: Дерево возражений (self-referential)
    - technical_insights: Технические заметки из совещаний
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, Float, Date, DateTime,
    ForeignKey, Boolean, func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


# ──────────────────────────────────────────────
# ENUM-типы
# ──────────────────────────────────────────────

class LeadStatus(str, enum.Enum):
    """Статусы сделок в воронке продаж."""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    NEGOTIATION = "negotiation"
    CONTRACT = "contract"
    WON = "won"
    LOST = "lost"
    STALE = "stale"


class ProductCategory(str, enum.Enum):
    """Категории продукции."""
    WATER = "water"
    STEAM = "steam"


class ActionItemStatus(str, enum.Enum):
    """Статусы задач/целей."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class ActionItemPriority(str, enum.Enum):
    """Приоритеты задач."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ──────────────────────────────────────────────
# employees — Сотрудники
# ──────────────────────────────────────────────

class Employee(Base):
    """Менеджеры по продажам и руководство. Заполняется при сидировании."""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(200), nullable=False)
    role = Column(String(100), nullable=False)
    regions = Column(Text, nullable=True)
    product_category = Column(SAEnum(ProductCategory), nullable=False)
    email = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Связи
    leads = relationship("Lead", back_populates="manager", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="manager", cascade="all, delete-orphan")
    transcripts = relationship("Transcript", back_populates="manager", cascade="all, delete-orphan")
    sales = relationship("Sale", back_populates="manager", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Employee {self.id}: {self.full_name}>"


# ──────────────────────────────────────────────
# crm_reports — Импортированные файлы отчётов
# ──────────────────────────────────────────────

class CrmReport(Base):
    """Один загруженный CRM-файл отчёта (CSV/Excel).

    Позволяет отслеживать историю импортов, метаданные файла
    и агрегированную статистику по нему.
    """
    __tablename__ = "crm_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(500), nullable=False)

    # Менеджер, чей отчёт (может быть None, если не удалось сопоставить)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    manager_name_raw = Column(String(200), nullable=True)  # имя из имени файла

    # Период отчёта (из имени файла)
    report_date_start = Column(Date, nullable=True)
    report_date_end = Column(Date, nullable=True)

    # Агрегаты
    total_rows = Column(Integer, default=0, nullable=False)
    total_amount = Column(Float, default=0.0, nullable=False)

    # Статус импорта: ok | partial | error
    status = Column(String(20), default="ok", nullable=False)
    error_message = Column(Text, nullable=True)

    imported_at = Column(DateTime, default=func.now(), nullable=False)

    # Связи
    manager = relationship("Employee", foreign_keys=[manager_id])
    leads = relationship("Lead", back_populates="crm_report")

    def __repr__(self) -> str:
        return f"<CrmReport {self.id}: {self.filename}>"


# ──────────────────────────────────────────────
# leads — Сделки/Лиды
# ──────────────────────────────────────────────

class Lead(Base):
    """Сделки из Excel/CSV отчётов CRM или ручного ввода."""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    # Колонки из Excel (русские названия маппятся при парсинге)
    update_date = Column(Date, nullable=True)
    status = Column(SAEnum(LeadStatus), default=LeadStatus.NEW, nullable=False)
    customer = Column(String(300), nullable=False)
    equipment = Column(String(300), nullable=True)
    amount = Column(Float, nullable=True)
    next_step = Column(Text, nullable=True)
    next_step_date = Column(Date, nullable=True)
    planned_shipment_date = Column(Date, nullable=True)

    # Служебные поля
    source = Column(String(100), nullable=True)
    upload_batch_id = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)

    # Привязка к файлу-отчёту (заполняется при импорте через CrmReport)
    crm_report_id = Column(Integer, ForeignKey("crm_reports.id"), nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Связи
    manager = relationship("Employee", back_populates="leads")
    action_items = relationship("ActionItem", back_populates="lead", cascade="all, delete-orphan")
    crm_report = relationship("CrmReport", back_populates="leads")

    def __repr__(self) -> str:
        return f"<Lead {self.id}: {self.customer}>"


# ──────────────────────────────────────────────
# action_items — Задачи/Цели
# ──────────────────────────────────────────────

class ActionItem(Base):
    """Задачи, цели и follow-up'ы с дедлайнами. Привязаны к менеджеру и опционально к сделке."""
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(ActionItemStatus), default=ActionItemStatus.PENDING, nullable=False)
    priority = Column(SAEnum(ActionItemPriority), default=ActionItemPriority.MEDIUM, nullable=False)
    due_date = Column(Date, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Связи
    manager = relationship("Employee", back_populates="action_items")
    lead = relationship("Lead", back_populates="action_items")

    def __repr__(self) -> str:
        return f"<ActionItem {self.id}: {self.title}>"


# ──────────────────────────────────────────────
# transcripts — Транскрипты совещаний
# ──────────────────────────────────────────────

class Transcript(Base):
    """Загруженные транскрипты совещаний (.txt/.md)."""
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    filename = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    meeting_date = Column(Date, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Связи
    manager = relationship("Employee", back_populates="transcripts")
    insights = relationship("TechnicalInsight", back_populates="transcript", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Transcript {self.id}: {self.filename}>"


# ──────────────────────────────────────────────
# sales — Зафиксированные продажи
# ──────────────────────────────────────────────

class Sale(Base):
    """Записи о завершённых продажах с серийными номерами и скидками."""
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manager_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)

    customer = Column(String(300), nullable=False)
    equipment = Column(String(300), nullable=True)
    serial_numbers = Column(Text, nullable=True)
    amount = Column(Float, nullable=False)
    discount = Column(Float, nullable=True)
    shipment_date = Column(Date, nullable=True)
    sale_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Связи
    manager = relationship("Employee", back_populates="sales")

    def __repr__(self) -> str:
        return f"<Sale {self.id}: {self.customer} — {self.amount}>"


# ──────────────────────────────────────────────
# objections — Дерево возражений (self-referential)
# ──────────────────────────────────────────────

class Objection(Base):
    """Иерархическое дерево возражений клиентов с рекомендуемыми ответами."""
    __tablename__ = "objections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_id = Column(Integer, ForeignKey("objections.id"), nullable=True)
    title = Column(String(500), nullable=False)
    response = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Self-referential связь (adjacency list)
    children = relationship(
        "Objection",
        cascade="all, delete-orphan",
        backref=("parent_rel", {"remote_side": [id]}),
    )

    def __repr__(self) -> str:
        return f"<Objection {self.id}: {self.title}>"


# ──────────────────────────────────────────────
# technical_insights — Технические заметки
# ──────────────────────────────────────────────

class TechnicalInsight(Base):
    """Технические заметки и инсайты, извлечённые из транскриптов или добавленные вручную."""
    __tablename__ = "technical_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transcript_id = Column(Integer, ForeignKey("transcripts.id"), nullable=True)
    author = Column(String(200), nullable=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(String(500), nullable=True)
    product_category = Column(SAEnum(ProductCategory), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Связи
    transcript = relationship("Transcript", back_populates="insights")

    def __repr__(self) -> str:
        return f"<TechnicalInsight {self.id}: {self.title}>"
