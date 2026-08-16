from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.schemas.gantt_schema import GanttData
from backend.services.gantt_service import GanttService, GanttValidationError

router = APIRouter(prefix="/gantt")

templates = Jinja2Templates(directory="backend/templates")
gantt_service = GanttService()


@router.get("/")
def gantt(
    request: Request,
    property_id: int | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    start, end = gantt_service.default_window()
    data = gantt_service.get_data(db, start, end, property_id, include_inactive)

    return templates.TemplateResponse(
        request=request,
        name="pages/gantt.html",
        context={
            "request": request,
            "version": "1.0.0",
            "current_page": "gantt",
            "gantt_data": data.model_dump(mode="json"),
            "selected_property_id": property_id,
            "include_inactive": include_inactive,
        },
    )


@router.get("/data", response_model=GanttData)
def gantt_data(
    start: date = Query(...),
    end: date = Query(...),
    property_id: int | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    try:
        return gantt_service.get_data(
            db, start, end, property_id, include_inactive
        )
    except GanttValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
