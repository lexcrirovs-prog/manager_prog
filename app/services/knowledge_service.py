"""Сервис базы знаний: построение дерева возражений и работа с инсайтами."""

from sqlalchemy.orm import Session

from app.database.models import Objection, TechnicalInsight, ProductCategory


def get_objection_tree(db: Session) -> list[dict]:
    """Строит вложенное дерево возражений из плоской таблицы.

    Возвращает список корневых узлов, каждый с вложенным 'children'.
    """
    all_objections = db.query(Objection).order_by(Objection.sort_order).all()

    # Индекс по id
    by_id = {}
    for obj in all_objections:
        by_id[obj.id] = {
            "id": obj.id,
            "parent_id": obj.parent_id,
            "title": obj.title,
            "response": obj.response,
            "category": obj.category,
            "sort_order": obj.sort_order,
            "children": [],
        }

    # Собираем дерево
    roots = []
    for obj_dict in by_id.values():
        parent_id = obj_dict["parent_id"]
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(obj_dict)
        else:
            roots.append(obj_dict)

    return roots


def get_insights(
    db: Session,
    search: str | None = None,
    category: ProductCategory | None = None,
) -> list[TechnicalInsight]:
    """Получение инсайтов с фильтрацией."""
    query = db.query(TechnicalInsight)

    if search:
        query = query.filter(
            TechnicalInsight.title.ilike(f"%{search}%")
            | TechnicalInsight.content.ilike(f"%{search}%")
        )
    if category:
        query = query.filter(TechnicalInsight.product_category == category)

    return query.order_by(TechnicalInsight.created_at.desc()).all()
