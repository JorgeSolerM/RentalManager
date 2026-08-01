from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory="backend/templates")


@router.get("/")
def dashboard(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="pages/dashboard.html",
        context={
            "request": request,
            "version": "1.0.0",
            "current_page": "dashboard",
        },
    )
