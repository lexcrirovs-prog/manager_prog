"""Роутер авторизации: вход, выход, смена пароля (заглушка)."""

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.database.models import Employee
from app.services.auth_service import verify_password, get_current_user

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_page(request: Request):
    from app.main import templates
    # Если уже залогинен — редиректим на главную
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=302)
    error = request.query_params.get("error")
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(Employee.username == username).first()
    if emp and emp.password_hash and verify_password(password, emp.password_hash):
        request.session["user_id"] = emp.id
        return RedirectResponse("/", status_code=302)
    return RedirectResponse("/login?error=1", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@router.get("/auth/set-password")
def set_password_page(request: Request):
    """Заглушка — установка пароля по ссылке из письма (в разработке)."""
    from app.main import templates
    return templates.TemplateResponse("set_password_stub.html", {"request": request})
