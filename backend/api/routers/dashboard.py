from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.services.dashboard_service import DashboardService

router = APIRouter()

templates = Jinja2Templates(directory="backend/templates")
dashboard_service = DashboardService()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):

    dashboard_data = dashboard_service.get_dashboard(db)

    return templates.TemplateResponse(
        request=request,
        name="pages/dashboard.html",
        context={
            "request": request,
            "current_page": "dashboard",
            "dashboard": dashboard_data,
        },
    )
