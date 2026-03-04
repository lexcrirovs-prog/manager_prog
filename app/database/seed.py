"""
Сидирование базы данных: начальные сотрудники и дерево возражений.

Выполняется один раз при первом запуске (если таблицы пусты).
"""

from sqlalchemy.orm import Session

from app.database.models import (
    Employee, Objection, ProductCategory,
)


SEED_EMPLOYEES = [
    {
        "full_name": "Александр Боев",
        "role": "CFO",
        "regions": "ЦФО (пар и вода)",
        "product_category": ProductCategory.WATER,
        "notes": "Руководитель — пар и вода, ЦФО",
    },
    {
        "full_name": "Григорий Варгазин",
        "role": "Региональный менеджер",
        "regions": "ЮФО, СКФО, Крым, новые регионы",
        "product_category": ProductCategory.WATER,
    },
    {
        "full_name": "Ракипов Рустам",
        "role": "Региональный менеджер",
        "regions": "Татарстан, Чебоксары, Удмуртия, Ульяновская обл., Башкортостан",
        "product_category": ProductCategory.WATER,
    },
    {
        "full_name": "Светлана Филаткина",
        "role": "Региональный менеджер",
        "regions": "Свердловская, Нижегородская, Тюменская, Челябинская обл. и восток",
        "product_category": ProductCategory.WATER,
    },
    {
        "full_name": "Евгений Ведмиденко",
        "role": "Региональный менеджер",
        "regions": "Саратовская, Пензенская, Самарская обл., Мордовия",
        "product_category": ProductCategory.WATER,
    },
    {
        "full_name": "Сергей Глинкин",
        "role": "Тех. директор",
        "regions": "Все регионы (кроме ЦФО) — паровые котлы",
        "product_category": ProductCategory.STEAM,
        "notes": "Паровые котлы — все регионы кроме ЦФО",
    },
]


SEED_OBJECTIONS = [
    {
        "title": "Ценовые возражения",
        "category": "price",
        "children": [
            {
                "title": "Слишком дорого",
                "response": "Сравните стоимость владения за 5 лет: наше оборудование окупается быстрее за счёт энергоэффективности и низких затрат на обслуживание.",
            },
            {
                "title": "У конкурента дешевле",
                "response": "Уточните комплектацию и гарантийные условия конкурента. Наша цена включает расширенную гарантию и сервисное сопровождение.",
            },
            {
                "title": "Нет бюджета в этом году",
                "response": "Предложите рассрочку или лизинг. Подготовьте расчёт ROI для обоснования перед руководством клиента.",
            },
        ],
    },
    {
        "title": "Технические возражения",
        "category": "technical",
        "children": [
            {
                "title": "Не подходит по параметрам",
                "response": "Предложите расчёт под конкретную задачу клиента. Привлеките тех. директора для подбора оптимальной конфигурации.",
            },
            {
                "title": "Сомнения в надёжности",
                "response": "Покажите статистику наработки на отказ, список референсных объектов и отзывы действующих клиентов.",
            },
        ],
    },
    {
        "title": "Организационные возражения",
        "category": "organizational",
        "children": [
            {
                "title": "Долгие сроки поставки",
                "response": "Покажите актуальный график производства. Предложите поэтапную поставку или аналог со склада.",
            },
            {
                "title": "Нужно согласование с руководством",
                "response": "Подготовьте презентацию и ТЭО для ЛПР. Предложите провести встречу с руководством клиента.",
            },
        ],
    },
]


def _seed_objections(db: Session, items: list[dict], parent_id: int | None = None) -> None:
    """Рекурсивное создание дерева возражений."""
    for i, item in enumerate(items):
        obj = Objection(
            parent_id=parent_id,
            title=item["title"],
            response=item.get("response"),
            category=item.get("category"),
            sort_order=i,
        )
        db.add(obj)
        db.flush()  # Получаем id для дочерних элементов

        children = item.get("children", [])
        if children:
            _seed_objections(db, children, parent_id=obj.id)


def seed_database(db: Session) -> None:
    """Заполняет БД начальными данными, если таблицы пусты."""
    if db.query(Employee).count() == 0:
        for emp_data in SEED_EMPLOYEES:
            db.add(Employee(**emp_data))
        db.commit()

    if db.query(Objection).count() == 0:
        _seed_objections(db, SEED_OBJECTIONS)
        db.commit()
