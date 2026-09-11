from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from backend.database.session import get_db
from backend.models.provider import Provider
from backend.models.owner_settlement import ExpenseCategory, Expense
from backend.services.provider_service import ProviderService

router = APIRouter(prefix='/providers')
templates = Jinja2Templates(directory='backend/templates')
service = ProviderService()


def page(request, db, mode, **context):
    response = templates.TemplateResponse(request=request,name='pages/providers.html',context={
        'request':request,'mode':mode,'settings_section':'providers','categories':list(db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name))),**context})
    response.headers['Cache-Control']='private, no-store'
    return response


@router.get('')
def listing(request: Request,q: str='',db=Depends(get_db)):
    return page(request,db,'list',items=service.list(db,q),q=q)


@router.get('/new')
def new(request: Request,db=Depends(get_db)):
    return page(request,db,'form',item=None,values={},from_expense=request.query_params.get('from_expense')=='1')


@router.post('/new')
async def create(request: Request,db=Depends(get_db)):
    form=dict(await request.form())
    try:
        item=service.save(db,**{**form,'active':form.get('active')=='1'})
        target=f'/expenses/new?provider_id={item.id}' if form.get('from_expense')=='1' else f'/providers/{item.id}'
        return RedirectResponse(target,303)
    except ValueError as exc:
        form['iban']=''
        return page(request,db,'form',item=None,values=form,error=str(exc),from_expense=form.get('from_expense')=='1')


def get(db,provider_id):
    item=db.get(Provider,provider_id)
    if item is None: raise HTTPException(404,'Proveedor no encontrado')
    return item


@router.post('/quick')
async def quick_create(request:Request,db=Depends(get_db)):
    form=await request.form()
    try:
        item=service.save(db,legal_name=form.get('legal_name'),default_expense_category_id=form.get('default_expense_category_id'),active=True)
        return {'id':item.id,'name':item.legal_name,'category_id':item.default_expense_category_id}
    except ValueError as exc:
        return JSONResponse({'error':str(exc)},status_code=400)


@router.get('/{provider_id}')
def detail(request: Request,provider_id:int,db=Depends(get_db)):
    item=get(db,provider_id)
    return page(request,db,'detail',item=item,linked=list(db.scalars(select(Expense).where(Expense.provider_id==item.id).order_by(Expense.expense_date.desc()))))


@router.get('/{provider_id}/edit')
def edit(request:Request,provider_id:int,db=Depends(get_db)):
    item=get(db,provider_id)
    values={key:getattr(item,key) or '' for key in (*service.fields,'iban','default_expense_category_id')}
    values['active']='1' if item.active else ''
    return page(request,db,'form',item=item,values=values,from_expense=False)


@router.post('/{provider_id}/edit')
async def update(request:Request,provider_id:int,db=Depends(get_db)):
    item=get(db,provider_id);form=dict(await request.form())
    try:
        service.save(db,provider_id,**{**form,'active':form.get('active')=='1'})
        return RedirectResponse(f'/providers/{provider_id}',303)
    except ValueError as exc:
        form['iban']=''
        return page(request,db,'form',item=item,values=form,error=str(exc),from_expense=False)


@router.post('/{provider_id}/active')
async def active(request:Request,provider_id:int,db=Depends(get_db)):
    get(db,provider_id)
    form=await request.form()
    service.set_active(db,provider_id,form.get('active')=='1')
    return RedirectResponse(f'/providers/{provider_id}',303)
