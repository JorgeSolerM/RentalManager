from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from backend.core.business_time import business_today
from backend.core.iban import mask_iban
from backend.database.session import get_db
from backend.models.booking import Booking
from backend.models.property import Property
from backend.models.room import Room
from backend.services.sepa_collection_service import SepaCollectionService

router = APIRouter(prefix="/collections")
templates = Jinja2Templates(directory="backend/templates")
service = SepaCollectionService()
STATUS = {"prepared": "Preparada", "exported": "Exportada", "presented": "Presentada", "partially_collected": "Parcialmente cobrada", "collected": "Cobrada", "cancelled":"Cancelada"}


def page(request, db, **context):
    http_status = context.pop("http_status", 200)
    return templates.TemplateResponse(request=request, name="pages/collections.html", context={
        "request": request, "today": business_today(), "states": STATUS, "mask_iban": mask_iban,
        "settings": service.settings(db), "error": None, "mode": "index", **context,
        "batch_label":service.batch_label,
        "debit_warnings":{d.id:service.balance_warning(db,d) for g in context['batch'].groups for d in g.debits} if context.get('batch') else {},
    }, status_code=http_status, headers={"Cache-Control": "private, no-store"})


@router.get("")
def index(request: Request, db=Depends(get_db)):
    return page(request, db, batches=service.list_batches(db))


@router.get("/new")
def new(request: Request, db=Depends(get_db)):
    return page(request, db, mode="new", properties=list(db.scalars(select(Property).order_by(Property.name, Property.id))))


@router.get("/{batch_id:int}")
def detail(request: Request, batch_id: int, db=Depends(get_db)):
    try:
        return page(request, db, mode="detail", batch=service.get_batch(db, batch_id))
    except ValueError as error:
        return page(request, db, batches=[], error=str(error), http_status=404)


@router.get("/artifacts/{artifact_id:int}")
def download(artifact_id: int, db=Depends(get_db)):
    from fastapi import HTTPException
    try:
        path = service.artifact_path(db, artifact_id)
    except ValueError:
        raise HTTPException(404, "Archivo no disponible.") from None
    return FileResponse(path, media_type="application/xml", filename=path.name,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{action}")
async def operate(request: Request, action: str, db=Depends(get_db)):
    form = await request.form()
    try:
        if action == "settings":
            service.save_settings(db, form.get("initiator_name", ""), form.get("initiator_identifier", ""))
            return RedirectResponse("/collections", status_code=303)
        if action not in {"preview", "create"}:
            raise ValueError("Acción no válida.")
        period = date.fromisoformat(str(form.get("period", "")) + "-01")
        collection_date = date.fromisoformat(str(form.get("collection_date", "")))
        properties = [int(i) for i in form.getlist("property_ids")]
        if action == "preview":
            rows = service.preview(db, period, properties, collection_date)
            bookings = list(db.scalars(select(Booking).join(Room).where(Room.property_id.in_(properties), Booking.check_in < date(period.year + (period.month == 12), period.month % 12 + 1, 1), Booking.check_out > period).options(joinedload(Booking.room))))
            return page(request, db, mode="preview", rows=rows, period=period, collection_date=collection_date,
                        property_ids=properties, bookings=bookings, request_key=str(uuid4()), batch_name=service.administrative_name(form.get('name')))
        batch = service.create(db, period, properties, collection_date,
                               [int(i) for i in form.getlist("charge_ids")], str(form.get("request_key", "")), name=form.get('name'))
        return RedirectResponse(f"/collections/{batch.id}", status_code=303)
    except (ValueError, TypeError):
        db.rollback()
        # Parsing errors must not echo user-supplied fields/identifiers.
        return page(request, db, batches=service.list_batches(db), error="Revise la configuración SEPA, la fecha y la selección de cargos. Vuelva a previsualizar antes de crear la remesa.", http_status=400)
    except SQLAlchemyError:
        db.rollback()
        return page(request, db, batches=[], error="No se pudo completar la operación de base de datos. No se ha guardado parcialmente la remesa.", http_status=500)


@router.post("/{batch_id:int}/{action}")
async def transition(request: Request, batch_id: int, action: str, db=Depends(get_db)):
    try:
        if action == 'rename':
            form = await request.form()
            service.rename(db, batch_id, form.get('name'))
        elif action == "export":
            service.export(db, batch_id)
        elif action == "present":
            service.present(db, batch_id)
        elif action == "collect":
            form = await request.form()
            try:
                effective_date = date.fromisoformat(str(form.get("effective_date", "")))
                ids = [int(i) for i in form.getlist("debit_ids")]
            except (ValueError, TypeError):
                raise ValueError("Fecha o selección de cobros no válida.") from None
            service.collect(db, batch_id, ids, effective_date)
        elif action in {'return','cancel'}:
            form=await request.form()
            try:
                ids=[int(i) for i in form.getlist('debit_ids')]
                returned_on=date.fromisoformat(str(form.get('returned_on',''))) if action=='return' else None
            except (ValueError,TypeError):
                raise ValueError('Fecha o selección no válida.') from None
            if action=='return':
                service.return_debits(db,batch_id,ids,returned_on,form.get('reason'),form.get('reference'))
            else:
                if form.get('confirm_cancellation')!='yes':
                    raise ValueError('Confirme la cancelación y que la remesa no se ha presentado al banco.')
                service.cancel(db,batch_id,ids)
        else:
            raise ValueError("Acción no válida.")
        return RedirectResponse(f"/collections/{batch_id}", status_code=303)
    except ValueError as error:
        db.rollback()
        return page(request, db, batches=service.list_batches(db), error=str(error), http_status=400)
    except (SQLAlchemyError, OSError):
        db.rollback()
        return page(request, db, batches=[], error="No se pudo completar la operación. Revise la disponibilidad del almacenamiento y la base de datos.", http_status=500)
