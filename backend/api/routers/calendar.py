from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/calendar")

templates = Jinja2Templates(directory="backend/templates")


@router.get("/")
def calendar(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="pages/calendar.html",
        context={
            "request": request,
            "version": "1.0.0",
            "current_page": "calendar",
        },
    )
