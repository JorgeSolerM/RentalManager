"""Private administration; every mutation is restricted to the declared test DB."""
from datetime import date
from uuid import uuid4
from fastapi import APIRouter,Depends,Request,HTTPException
from fastapi.responses import RedirectResponse,Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.database.session import get_db
from backend.core.invoicing_config import invoicing_config,require_synthetic_invoicing
from backend.core.fee_tax import tax_configuration,TREATMENTS
from backend.models import Owner,Property
from backend.models.owner_settlement import ManagementFeeTerms,OwnerSettlementLine,OwnerSettlement
from backend.models.fee_billing import (InvoiceIssuerProfile,InvoiceSeries,OwnerFiscalIdentity,FeeTaxConfiguration,
    ManagementFeeInvoice,InvoiceFiscalRecord,FiscalSubmission,InvoiceRectificationNotice)
from backend.services.fee_invoice_service import FeeInvoiceService,identity_errors
from backend.services.financial_transaction import financial_transaction

router=APIRouter()
templates=Jinja2Templates(directory='backend/templates')
service=FeeInvoiceService()


def enabled():
    if not invoicing_config().enabled: raise HTTPException(404)


def page(request,db,mode,**context):
    enabled()
    return templates.TemplateResponse(request=request,name='pages/fee_invoicing.html',context=dict(
        request=request,mode=mode,key=str(uuid4()),settings_section='invoicing',**context))


def settings(request,db,error=None):
    return page(request,db,'settings',error=error,tab=request.query_params.get('tab','issuer'),
        issuers=list(db.scalars(select(InvoiceIssuerProfile).order_by(InvoiceIssuerProfile.id.desc()))),
        series=list(db.scalars(select(InvoiceSeries))),terms=list(db.scalars(select(ManagementFeeTerms))),
        tax_configs={c.terms_id:c.configuration for c in db.scalars(select(FeeTaxConfiguration))},
        owners=list(db.scalars(select(Owner))),properties={p.id:p.name for p in db.scalars(select(Property))},
        identities={i.owner_id:i for i in db.scalars(select(OwnerFiscalIdentity))},treatments=TREATMENTS)


@router.get('/settings/invoicing')
def configuration(request:Request,db=Depends(get_db)):
    enabled();return settings(request,db)


@router.post('/settings/invoicing/{section}')
async def configure(section:str,request:Request,db=Depends(get_db)):
    enabled();f=await request.form()
    try:
        require_synthetic_invoicing(db)
        with financial_transaction(db):
            if section=='issuer':
                identity={key:str(f.get(key,'')).strip() for key in ('name','tax_id','address','postal_code','city','province','country','email','phone')}
                identity.update(identification_type='NIF',identification_country='ES',
                    system={key:str(f.get('system_'+key,'')).strip() for key in ('name','id','version','installation','producer_name','producer_nif')})
                errors=identity_errors(identity,issuer=True)
                if errors: raise ValueError(' '.join(errors))
                db.add(InvoiceIssuerProfile(identity=identity,active=True))
            elif section=='series':
                issuer=db.get(InvoiceIssuerProfile,int(f['issuer_id']))
                prefix=f['prefix'].strip();padding=int(f['padding'])
                if not issuer or not prefix or len(prefix)>40 or not 1<=padding<=12 or any(not 32<=ord(c)<=126 for c in prefix):
                    raise ValueError('Revise emisor, prefijo y número de dígitos.')
                if f['document_type'] not in {'ordinary','rectifying'}: raise ValueError('Tipo documental no válido.')
                for existing in db.scalars(select(InvoiceSeries).where(InvoiceSeries.prefix==prefix)):
                    if db.get(InvoiceIssuerProfile,existing.issuer_id).identity['tax_id']==issuer.identity['tax_id']:
                        raise ValueError('Este NIF ya tiene ese prefijo en otra versión del emisor. Conserve su serie o utilice otra distinta.')
                db.add(InvoiceSeries(issuer_id=issuer.id,name=f['name'].strip(),prefix=prefix,padding=padding,
                    document_type=f['document_type'],fiscal_year=int(f['fiscal_year']) if f.get('fiscal_year') else None,active=True,counter=0))
            elif section=='series-status':
                series=db.get(InvoiceSeries,int(f['series_id']))
                if not series: raise ValueError('Serie no encontrada.')
                series.active=f.get('active')=='true'
            elif section=='tax':
                terms=db.get(ManagementFeeTerms,int(f['terms_id']))
                if not terms: raise ValueError('Versión de honorarios no encontrada.')
                if db.scalar(select(OwnerSettlementLine.id).where(OwnerSettlementLine.fee_terms_id==terms.id).limit(1)):
                    raise ValueError('Fiscalidad utilizada: cree una nueva versión de condiciones.')
                config=tax_configuration(dict(f))
                if str(terms.vat_rate)!=config['vat_rate'] or str(terms.withholding_rate)!=config['withholding_rate']:
                    raise ValueError('IVA/retención deben coincidir con esta versión de honorarios.')
                row=db.scalar(select(FeeTaxConfiguration).where(FeeTaxConfiguration.terms_id==terms.id))
                if row: row.configuration=config
                else: db.add(FeeTaxConfiguration(terms_id=terms.id,configuration=config))
            elif section=='owner':
                owner=db.get(Owner,int(f['owner_id']))
                if not owner: raise ValueError('Propietario no encontrado.')
                identity={key:str(f.get(key,'')).strip() for key in ('name','tax_id','address','postal_code','city','province','country','identification_type','identification_country')}
                errors=identity_errors(identity)
                if errors: raise ValueError(' '.join(errors))
                for key,target in [('name','legal_name'),('tax_id','tax_id'),('address','address_line'),('postal_code','postal_code'),('city','city'),('province','province'),('country','country')]:
                    setattr(owner,target,identity[key])
                row=db.get(OwnerFiscalIdentity,owner.id)
                if not row: row=OwnerFiscalIdentity(owner_id=owner.id);db.add(row)
                row.identification_type=identity['identification_type'];row.identification_country=identity['identification_country']
            else: raise ValueError('Sección no válida.')
        return RedirectResponse('/settings/invoicing?tab='+('tax' if section=='tax' else 'series' if section.startswith('series') else 'issuer'),303)
    except IntegrityError:
        db.rollback();return settings(request,db,'La configuración ya existe o no permite esa modificación. Revise los datos.')
    except (ValueError,KeyError) as exc:
        db.rollback();return settings(request,db,str(exc))


@router.get('/settlements/{settlement_id}/invoice')
def invoice_preview(settlement_id:int,request:Request,db=Depends(get_db)):
    enabled()
    existing=db.scalar(select(ManagementFeeInvoice).where(ManagementFeeInvoice.settlement_id==settlement_id))
    if existing and existing.status=='issued': return RedirectResponse(f'/invoices/{existing.id}',303)
    series=list(db.scalars(select(InvoiceSeries).where(InvoiceSeries.active==True,InvoiceSeries.document_type=='ordinary')))
    view=None;error=None
    try:
        if request.query_params.get('series_id'):
            operation=request.query_params.get('operation_date')
            view=service.preview(db,settlement_id,int(request.query_params['series_id']),
                date.fromisoformat(request.query_params.get('issue_date') or str(date.today())),
                date.fromisoformat(operation) if operation else None)
    except ValueError as exc: error=str(exc)
    return page(request,db,'preview',settlement_id=settlement_id,series=series,view=view,error=error,
                summary=service.summary(db,settlement_id),today=str(date.today()))


@router.post('/settlements/{settlement_id}/invoice')
async def invoice_draft(settlement_id:int,request:Request,db=Depends(get_db)):
    enabled();f=await request.form()
    try:
        item=service.draft(db,settlement_id,int(f['series_id']),date.fromisoformat(f['issue_date']),f['fingerprint'],f['request_key'],
            date.fromisoformat(f['operation_date']) if f.get('operation_date') else None)
        return RedirectResponse(f'/invoices/{item.id}',303)
    except (ValueError,KeyError) as exc:
        return page(request,db,'error',error=str(exc),back=f'/settlements/{settlement_id}/invoice')


@router.get('/invoices/{invoice_id}')
def invoice_detail(invoice_id:int,request:Request,db=Depends(get_db)):
    enabled();item=db.get(ManagementFeeInvoice,invoice_id)
    if not item: raise HTTPException(404)
    record=db.scalar(select(InvoiceFiscalRecord).where(InvoiceFiscalRecord.invoice_id==item.id,InvoiceFiscalRecord.kind=='alta'))
    submission=db.scalar(select(FiscalSubmission).where(FiscalSubmission.record_id==record.id)) if record else None
    return page(request,db,'invoice',item=item,view=item.snapshot,submission=submission,summary=service.summary(db,item.settlement_id))


@router.post('/invoices/{invoice_id}/issue')
async def invoice_issue(invoice_id:int,request:Request,db=Depends(get_db)):
    enabled();f=await request.form()
    try:
        service.issue(db,invoice_id,f['fingerprint'])
        return RedirectResponse(f'/invoices/{invoice_id}',303)
    except (ValueError,KeyError) as exc: return page(request,db,'error',error=str(exc),back=f'/invoices/{invoice_id}')


@router.get('/invoices/{invoice_id}/pdf')
def invoice_pdf(invoice_id:int,db=Depends(get_db)):
    enabled();require_synthetic_invoicing(db)
    item=db.get(ManagementFeeInvoice,invoice_id)
    if not item or item.status!='issued': raise HTTPException(404)
    from backend.services.fee_invoice_pdf import render_invoice
    return Response(render_invoice(item.snapshot),media_type='application/pdf',headers={
        'Content-Disposition':f'inline; filename="factura-prueba-{invoice_id}.pdf"',
        'Cache-Control':'private, no-store','X-Robots-Tag':'noindex, nofollow','X-Content-Type-Options':'nosniff'})
