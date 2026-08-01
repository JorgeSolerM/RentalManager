from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/gantt")

templates = Jinja2Templates(directory="backend/templates")


@router.get("/")
def gantt(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="pages/gantt.html",
        context={
            "request": request,
            "version": "1.0.0",
            "current_page": "gantt",
        },
    )
