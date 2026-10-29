"""Synthetic-only invoice issuance: one locked transaction, no network transport."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal as D
from zoneinfo import ZoneInfo
from sqlalchemy import select, update, and_, or_

from backend.core.invoicing_config import require_synthetic_invoicing
from backend.core.fee_tax import verifactu_tax_detail
from backend.core.verifactu_primitives import alta_hash, test_qr_url
from backend.models import Owner, Property, Payment, PaymentAllocation
from backend.models.owner_settlement import OwnerSettlement, OwnerSettlementLine
from backend.models.fee_billing import (InvoiceIssuerProfile, InvoiceSeries, OwnerFiscalIdentity,
    ManagementFeeInvoice, ManagementFeeInvoiceLine, ManagementFeeInvoiceSource, InvoiceFiscalRecord,
    FiscalChainState, FiscalSubmission, FiscalSubmissionAttempt, InvoiceRectificationNotice,
    FeeObligation, FeeCompensation, FeeObligationAdjustment)
from backend.services.expense_service import fingerprint, request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import ZERO, money


def identity_errors(identity, *, issuer=False):
    errors=[]
    for key in ('name','tax_id','address','postal_code','city','country','identification_type'):
        if not identity.get(key): errors.append(f'Falta dato fiscal: {key}.')
    if len(identity.get('name',''))>120: errors.append('El nombre fiscal supera 120 caracteres.')
    import re
    if not re.fullmatch('[A-Z]{2}',identity.get('country','')): errors.append('Indique país de domicilio en formato ISO de dos letras.')
    if identity.get('identification_country') and not re.fullmatch('[A-Z]{2}',identity['identification_country']):
        errors.append('Indique país de identificación en formato ISO de dos letras.')
    kind=identity.get('identification_type')
    if kind not in {'NIF','02','03','04','05','06'}: errors.append('Seleccione tipo de identificación fiscal.')
    if kind=='NIF':
        import re
        if not re.fullmatch(r'[A-Z0-9]{9}',identity.get('tax_id','')): errors.append('Formato de NIF no válido.')
    elif len(identity.get('tax_id',''))>20 or not identity.get('identification_country'):
        errors.append('Identificación extranjera: indique país y documento de hasta 20 caracteres.')
    if issuer and kind!='NIF': errors.append('El emisor de este perfil debe disponer de NIF español.')
    if issuer:
        system=identity.get('system',{})
        for key,limit in (('name',30),('id',2),('version',50),('installation',100),('producer_name',120),('producer_nif',9)):
            if not system.get(key) or len(system[key])>limit: errors.append(f'Identificación del SIF incompleta: {key}.')
    return errors


class FeeInvoiceService:
    def summary(self, db, settlement_id):
        obligations=list(db.scalars(select(FeeObligation).where(FeeObligation.settlement_id==settlement_id,FeeObligation.kind=='management_fee')))
        ids=[o.id for o in obligations]
        generated=sum((o.amount for o in obligations),ZERO)
        corrections=sum(db.scalars(select(FeeObligationAdjustment.amount).where(FeeObligationAdjustment.obligation_id.in_(ids))),ZERO)
        apps=list(db.scalars(select(FeeCompensation).where(FeeCompensation.obligation_id.in_(ids))))
        compensated=sum((a.amount if a.direction=='application' else -a.amount for a in apps),ZERO)
        invoice=db.scalar(select(ManagementFeeInvoice).where(ManagementFeeInvoice.settlement_id==settlement_id))
        notices=list(db.scalars(select(InvoiceRectificationNotice).where(InvoiceRectificationNotice.invoice_id==invoice.id))) if invoice else []
        pending_return=False
        if invoice and invoice.status=='issued':
            source_ids=[line['source_id'] for line in invoice.snapshot['lines']]
            originals=list(db.scalars(select(PaymentAllocation).join(OwnerSettlementLine,
                OwnerSettlementLine.payment_allocation_id==PaymentAllocation.id).where(OwnerSettlementLine.id.in_(source_ids))))
            if originals:
                pending_return=bool(db.scalar(select(PaymentAllocation.id).join(Payment).where(
                    Payment.direction=='refund',Payment.lifecycle=='posted',or_(*(and_(
                        Payment.corrects_payment_id==a.payment_id,PaymentAllocation.charge_id==a.charge_id) for a in originals))).limit(1)))
        return dict(generated=str(generated),corrected=str(corrections),compensated=str(compensated),
            pending=str(generated+corrections-compensated),invoiced=invoice.snapshot['net_payable'] if invoice and invoice.status=='issued' else '0.00',
            invoice=invoice,rectification_pending=bool(notices) or pending_return)

    def preview(self, db, settlement_id, series_id, issue_date, operation_date=None):
        settlement=db.get(OwnerSettlement,settlement_id)
        if not settlement or settlement.status!='closed' or not settlement.selection.get('billing'):
            raise ValueError('Se requiere una liquidación fiscal cerrada con snapshots completos.')
        series=db.get(InvoiceSeries,series_id)
        if not series: raise ValueError('Seleccione una serie.')
        issuer=db.get(InvoiceIssuerProfile,series.issuer_id)
        owner=db.get(Owner,settlement.owner_id);fiscal=db.get(OwnerFiscalIdentity,owner.id)
        recipient=dict(name=owner.legal_name,tax_id=owner.tax_id or '',address=owner.address_line or '',
            postal_code=owner.postal_code or '',city=owner.city or '',province=owner.province or '',country=owner.country or '',
            identification_type=fiscal.identification_type if fiscal else '',
            identification_country=fiscal.identification_country if fiscal else '')
        warnings=identity_errors(issuer.identity,issuer=True)+identity_errors(recipient)
        if not issuer.active or not series.active or series.document_type!='ordinary': warnings.append('Emisor o serie no disponible para factura ordinaria.')
        if series.fiscal_year and series.fiscal_year!=issue_date.year: warnings.append('La fecha no corresponde al ejercicio de la serie.')
        sources=list(db.scalars(select(OwnerSettlementLine).where(OwnerSettlementLine.settlement_id==settlement_id).order_by(OwnerSettlementLine.property_id,OwnerSettlementLine.id)))
        lines=[];signatures=set()
        for source in sources:
            snap=source.snapshot.get('fiscal_snapshot')
            if not snap: continue
            if money(snap['fee_base'],signed=True)<0:
                warnings.append('Pendiente de rectificación: no se emiten facturas ordinarias con correcciones negativas.')
            detail=verifactu_tax_detail(snap)
            signatures.add(snap['fee_signature']['digest'])
            if D(snap['fee_base']) or D(snap['fee_vat']):
                frozen_names=settlement.snapshot.get('document_identity',{}).get('properties',{})
                name=frozen_names.get(str(source.property_id))
                if not name: warnings.append('Falta el nombre de finca congelado; revisar la liquidación.')
                lines.append(dict(source_id=source.id,property_id=source.property_id,property_name=name or 'Finca sin identificar',
                    concept='Honorarios de gestión',snapshot=deepcopy(snap),tax_detail=detail))
        if not lines: warnings.append('No hay honorarios facturables.')
        if len(signatures)>1: warnings.append('La liquidación no es fiscalmente homogénea.')
        dates=sorted({l['snapshot']['operation_date'] for l in lines})
        selected=str(operation_date) if operation_date else dates[0] if len(dates)==1 else None
        if selected is None: warnings.append('Indique expresamente la fecha fiscal de la factura; existen varias fechas de operación.')
        if selected and date.fromisoformat(selected)>issue_date: warnings.append('La operación no puede ser posterior a la expedición.')
        base=sum((D(l['snapshot']['fee_base']) for l in lines),ZERO)
        vat=sum((D(l['snapshot']['fee_vat']) for l in lines),ZERO)
        withheld=sum((D(l['snapshot']['fee_withholding']) for l in lines),ZERO)
        payload=dict(settlement_id=settlement_id,owner_id=owner.id,series_id=series_id,issuer_id=issuer.id,
            series_identity=dict(prefix=series.prefix,padding=series.padding,document_type=series.document_type,fiscal_year=series.fiscal_year),
            issuer=deepcopy(issuer.identity),recipient=recipient,period_start=str(settlement.period_start),period_end=str(settlement.period_end),
            issue_date=str(issue_date),operation_date=selected,operation_dates=dates,lines=lines,
            fee_base=str(base),fee_vat=str(vat),fee_withholding=str(withheld),gross_invoice_total=str(base+vat),
            net_payable=str(base+vat-withheld),warnings=sorted(set(warnings)),synthetic=True)
        return {**payload,'fingerprint':fingerprint(payload)}

    def draft(self, db, settlement_id, series_id, issue_date, expected, request_key, operation_date=None):
        require_synthetic_invoicing(db)
        key=request_id(request_key)
        with financial_transaction(db):
            existing=db.scalar(select(ManagementFeeInvoice).where(ManagementFeeInvoice.settlement_id==settlement_id))
            if existing:
                if existing.status=='issued' or existing.fingerprint==expected: return existing
            view=self.preview(db,settlement_id,series_id,issue_date,operation_date)
            if view['fingerprint']!=expected: raise ValueError('Preview desactualizado; vuelva a revisar.')
            if existing:
                # Explicitly reviewed replacement of an unnumbered draft only.
                existing.series_id=series_id;existing.issuer_id=view['issuer_id']
                existing.issue_date=issue_date;existing.snapshot=view;existing.fingerprint=expected
                return existing
            invoice=ManagementFeeInvoice(settlement_id=settlement_id,owner_id=view['owner_id'],issuer_id=view['issuer_id'],
                series_id=series_id,issue_date=issue_date,snapshot=view,fingerprint=expected,request_key=key,status='draft')
            db.add(invoice)
        return invoice

    def issue(self, db, invoice_id, expected):
        config=require_synthetic_invoicing(db)
        if not config.verifactu_enabled: raise ValueError('Active la preparación VERI*FACTU en el entorno sintético.')
        with financial_transaction(db):
            invoice=db.get(ManagementFeeInvoice,invoice_id)
            if not invoice or invoice.fingerprint!=expected: raise ValueError('Borrador no válido.')
            if invoice.status=='issued': return invoice
            view=self.preview(db,invoice.settlement_id,invoice.series_id,invoice.issue_date,
                              date.fromisoformat(invoice.snapshot['operation_date']) if invoice.snapshot.get('operation_date') else None)
            if view['fingerprint']!=expected: raise ValueError('Datos fiscales desactualizados: revise el borrador.')
            if view['warnings']: raise ValueError(' '.join(view['warnings']))
            series=db.get(InvoiceSeries,invoice.series_id)
            counter=db.scalar(update(InvoiceSeries).where(InvoiceSeries.id==series.id,InvoiceSeries.active==True)
                              .values(counter=InvoiceSeries.counter+1).returning(InvoiceSeries.counter))
            if counter is None: raise ValueError('Serie no disponible.')
            last_date=db.scalar(select(ManagementFeeInvoice.issue_date).where(
                ManagementFeeInvoice.series_id==series.id,ManagementFeeInvoice.status=='issued')
                .order_by(ManagementFeeInvoice.issue_date.desc()).limit(1))
            if last_date and invoice.issue_date<last_date: raise ValueError('La fecha de expedición no puede retroceder dentro de la serie.')
            number=series.prefix+str(counter).zfill(series.padding)
            if len(number)>60: raise ValueError('Se ha agotado el formato de numeración.')
            duplicate=db.scalar(select(ManagementFeeInvoice.id).where(ManagementFeeInvoice.number==number,
                ManagementFeeInvoice.status=='issued',ManagementFeeInvoice.snapshot['issuer']['tax_id'].as_string()==view['issuer']['tax_id']))
            if duplicate: raise ValueError('Número ya emitido para este NIF. Revise la serie; no se consume numeración.')
            stamp=datetime.now(ZoneInfo('Europe/Madrid')).replace(microsecond=0)
            view=deepcopy(view);view.update(number=number,issued_at=stamp.isoformat(),document_type='F1')
            view['qr_url']=test_qr_url(issuer_nif=view['issuer']['tax_id'],number=number,issue_date=invoice.issue_date,
                                       gross_invoice_total=view['gross_invoice_total'])
            invoice.number=number;invoice.status='issued';invoice.issued_at=stamp.replace(tzinfo=None);invoice.snapshot=view
            for source in view['lines']:
                line=ManagementFeeInvoiceLine(invoice_id=invoice.id,property_id=source['property_id'],snapshot=source)
                db.add(line);db.flush()
                db.add(ManagementFeeInvoiceSource(line_id=line.id,source_id=source['source_id']))
            identity=view['issuer'];system=identity['system']
            chain_key=f"{identity['tax_id']}|{system['id']}|{system['installation']}|test"
            chain=db.get(FiscalChainState,chain_key)
            if not chain:
                chain=FiscalChainState(chain_key=chain_key);db.add(chain);db.flush()
            prior=db.get(InvoiceFiscalRecord,chain.last_record_id) if chain.last_record_id else None
            payload=dict(IDEmisorFactura=identity['tax_id'],NumSerieFactura=number,
                FechaExpedicionFactura=invoice.issue_date.strftime('%d-%m-%Y'),TipoFactura='F1',
                CuotaTotal=view['fee_vat'],ImporteTotal=view['gross_invoice_total'],Huella=chain.last_hash or '',
                FechaHoraHusoGenRegistro=stamp.isoformat(),FechaOperacion=date.fromisoformat(view['operation_date']).strftime('%d-%m-%Y'),
                NombreRazonEmisor=identity['name'],Destinatario=view['recipient'],SistemaInformatico=system,
                Desglose=[l['tax_detail'] for l in view['lines']],DescripcionOperacion='Honorarios de gestión de alquileres',
                RegistroAnterior={k:prior.payload[k] for k in ('IDEmisorFactura','NumSerieFactura','FechaExpedicionFactura')} if prior else None)
            taxpayers=set(db.scalars(select(ManagementFeeInvoice.snapshot['issuer']['tax_id'].as_string()).where(ManagementFeeInvoice.status=='issued')))
            taxpayers.add(identity['tax_id']);payload['multiple_taxpayers']='S' if len(taxpayers)>1 else 'N'
            digest=alta_hash(payload)
            record=InvoiceFiscalRecord(invoice_id=invoice.id,chain_key=chain_key,kind='alta',payload=payload,
                generated_at=stamp.isoformat(),hash=digest,previous_record_id=chain.last_record_id)
            db.add(record);db.flush();chain.last_record_id=record.id;chain.last_hash=digest
            db.add(FiscalSubmission(record_id=record.id,status='pending',environment='test',attempts=0))
        return invoice

    def mock_submission(self, db, submission_id, outcome):
        """Local test harness only: never invokes a URL or reads a certificate."""
        require_synthetic_invoicing(db)
        allowed={'accepted','accepted_with_errors','rejected','unknown','retry_pending'}
        if outcome not in allowed: raise ValueError('Resultado sintético no válido.')
        with financial_transaction(db):
            item=db.get(FiscalSubmission,submission_id)
            if not item or item.environment!='test': raise ValueError('Solo remisiones de prueba.')
            if item.status in {'accepted','accepted_with_errors'}: return item
            item.attempts+=1;item.status=outcome
            db.add(FiscalSubmissionAttempt(submission_id=item.id,result=outcome,response={'synthetic':True,'result':outcome}))
        return item
