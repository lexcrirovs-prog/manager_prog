"""База знаний: дерево возражений и технические инсайты."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import Objection, TechnicalInsight, ProductCategory

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("")
def knowledge_home(request: Request, db: Session = Depends(get_db)):
    """Главная страница базы знаний."""
    from app.main import templates

    objection_count = db.query(Objection).count()
    insight_count = db.query(TechnicalInsight).count()

    return templates.TemplateResponse("knowledge_base.html", {
        "request": request,
        "objection_count": objection_count,
        "insight_count": insight_count,
    })


@router.get("/objections")
def objections_tree(request: Request, db: Session = Depends(get_db)):
    """Дерево возражений — интерактивный mindmap."""
    from app.main import templates
    from app.services.knowledge_service import get_objection_tree

    tree = get_objection_tree(db)

    return templates.TemplateResponse("objections_tree.html", {
        "request": request,
        "tree": tree,
    })


@router.post("/objections/new")
async def add_objection(
    title: str = Form(...),
    response: str = Form(""),
    category: str = Form(""),
    parent_id: int = Form(None),
    db: Session = Depends(get_db),
):
    """Добавление нового узла в дерево возражений."""
    obj = Objection(
        parent_id=parent_id if parent_id else None,
        title=title,
        response=response or None,
        category=category or None,
    )
    db.add(obj)
    db.commit()
    return RedirectResponse("/knowledge/objections", status_code=302)


@router.post("/objections/{objection_id}/edit")
async def edit_objection(
    objection_id: int,
    title: str = Form(...),
    response: str = Form(""),
    category: str = Form(""),
    db: Session = Depends(get_db),
):
    """Редактирование узла дерева возражений."""
    obj = db.query(Objection).get(objection_id)
    if obj:
        obj.title = title
        obj.response = response or None
        obj.category = category or None
        db.commit()
    return RedirectResponse("/knowledge/objections", status_code=302)


@router.post("/objections/{objection_id}/delete")
async def delete_objection(objection_id: int, db: Session = Depends(get_db)):
    """Удаление узла и всех дочерних элементов."""
    obj = db.query(Objection).get(objection_id)
    if obj:
        db.delete(obj)
        db.commit()
    return RedirectResponse("/knowledge/objections", status_code=302)


@router.get("/insights")
def insights_list(
    request: Request,
    search: str = None,
    category: str = None,
    db: Session = Depends(get_db),
):
    """Реестр технических инсайтов с поиском и фильтрацией."""
    from app.main import templates

    query = db.query(TechnicalInsight)
    if search:
        query = query.filter(
            TechnicalInsight.title.ilike(f"%{search}%")
            | TechnicalInsight.content.ilike(f"%{search}%")
            | TechnicalInsight.tags.ilike(f"%{search}%")
        )
    if category:
        query = query.filter(TechnicalInsight.product_category == category)

    insights = query.order_by(TechnicalInsight.created_at.desc()).all()
    categories = [c.value for c in ProductCategory]

    return templates.TemplateResponse("technical_insights.html", {
        "request": request,
        "insights": insights,
        "categories": categories,
        "filter_search": search,
        "filter_category": category,
    })


@router.post("/insights/new")
async def add_insight(
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(""),
    tags: str = Form(""),
    product_category: str = Form(""),
    db: Session = Depends(get_db),
):
    """Добавление технического инсайта вручную."""
    insight = TechnicalInsight(
        title=title,
        content=content,
        author=author or None,
        tags=tags or None,
        product_category=ProductCategory(product_category) if product_category else None,
    )
    db.add(insight)
    db.commit()
    return RedirectResponse("/knowledge/insights", status_code=302)


@router.post("/insights/{insight_id}/edit")
async def edit_insight(
    insight_id: int,
    title: str = Form(...),
    content: str = Form(...),
    author: str = Form(""),
    tags: str = Form(""),
    product_category: str = Form(""),
    db: Session = Depends(get_db),
):
    """Редактирование технического инсайта."""
    insight = db.query(TechnicalInsight).get(insight_id)
    if insight:
        insight.title = title
        insight.content = content
        insight.author = author or None
        insight.tags = tags or None
        insight.product_category = ProductCategory(product_category) if product_category else None
        db.commit()
    return RedirectResponse("/knowledge/insights", status_code=302)


@router.post("/insights/{insight_id}/delete")
async def delete_insight(insight_id: int, db: Session = Depends(get_db)):
    """Удаление технического инсайта."""
    insight = db.query(TechnicalInsight).get(insight_id)
    if insight:
        db.delete(insight)
        db.commit()
    return RedirectResponse("/knowledge/insights", status_code=302)
