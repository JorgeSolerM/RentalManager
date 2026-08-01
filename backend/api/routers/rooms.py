from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/rooms")

templates = Jinja2Templates(directory="backend/templates")


@router.get("/")
def rooms(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="pages/rooms.html",
        context={
            "request": request,
            "version": "1.0.0",
            "current_page": "rooms",
        },
    )
