"""Homogeneous settlements with source-level obligations and cash applications."""
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
from uuid import UUID, uuid5
from sqlalchemy import select

from backend.core.fee_tax import fiscal_snapshot, fee_signature, TREATMENTS
from backend.core.fee_grouping import group_fee_sources
from backend.core.fee_compensation import Obligation, compensation_plan
from backend.core.invoicing_config import require_synthetic_invoicing
from backend.models import Owner, Property, PaymentAllocation
from backend.models.owner_settlement import OwnerSettlement, OwnerSettlementLine, ManagementFeeTerms
from backend.models.fee_billing import (FeeTaxConfiguration, FeeObligation, FeeObligationAdjustment,
    FeeFund, FeeCompensation, ManagementFeeInvoiceSource, ManagementFeeInvoiceLine, ManagementFeeInvoice,
    InvoiceRectificationNotice)
from backend.services.owner_settlement_service import OwnerSettlementService, now
from backend.services.settlement_selection_service import SettlementSelectionService
from backend.services.expense_service import fingerprint, request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import ZERO, money


class BillingSettlementService:
    def __init__(self):
        self.legacy = OwnerSettlementService()

    def catalog(self, db, start, end, property_ids=None):
        result=SettlementSelectionService(legacy=True).catalog(db, start, end, property_ids)
        for prop in result:
            for owner in prop['owners']:
                rows=[r for r in owner['view']['rows'] if r['kind']!='prior_balance']
                owner['has_movements']=bool(rows)
                for row in rows:
                    if row.get('fee_terms_id') and not row.get('fiscal_snapshot'):
                        config=db.scalar(select(FeeTaxConfiguration).where(FeeTaxConfiguration.terms_id==row['fee_terms_id']))
                        if config is None:prop['errors'].append('Configure la fiscalidad de la versión de honorarios aplicable.')
            prop['errors']=list(dict.fromkeys(prop['errors']))
            prop['state']='review' if prop['errors'] else 'ready' if any(o['has_movements'] for o in prop['owners']) else 'empty'
        return result

    def _state(self, db, owner_id):
        obligations = list(db.scalars(select(FeeObligation).where(FeeObligation.owner_id == owner_id)))
        ids = [o.id for o in obligations]
        adjustments = list(db.scalars(select(FeeObligationAdjustment).where(FeeObligationAdjustment.obligation_id.in_(ids))))
        applications = list(db.scalars(select(FeeCompensation).where(FeeCompensation.obligation_id.in_(ids))))
        return {o.source_key: dict(key=o.source_key, kind=o.kind, date=str(o.effective_date),
            generated=str(o.amount + sum((a.amount for a in adjustments if a.obligation_id == o.id), ZERO)),
            compensated=str(sum((a.amount if a.direction == 'application' else -a.amount
                                 for a in applications if a.obligation_id == o.id), ZERO))) for o in obligations}

    def _fiscal(self, db, row, operation_dates):
        if not row.get('fee_terms_id'):
            return None
        terms = db.get(ManagementFeeTerms, row['fee_terms_id'])
        frozen = row.get('fiscal_snapshot')
        if frozen:
            # A refund copies the original fiscal treatment/rates, not current
            # configuration. Only signed source amounts and correction date vary.
            snap=deepcopy(frozen)
            operation=operation_dates.get(row['key'])
            if snap['operation_date_policy']=='explicit' and not operation:
                raise ValueError('Indique la fecha fiscal de operación; no se infiere del cierre.')
            snap.update(fee_base=row['fee_base'],fee_vat=row['fee_vat'],fee_withholding=row['fee_withholding'],
                fee_net=row['fee'],net_payable=row['fee'],gross_invoice_total=str(D(row['fee_base'])+D(row['fee_vat'])),
                receipt_date=row['date'],operation_date=operation or row['date'],source_key=row['key'])
            return snap
        config = frozen or db.scalar(select(FeeTaxConfiguration).where(FeeTaxConfiguration.terms_id == terms.id))
        config = config if isinstance(config, dict) else config.configuration if config else None
        if config is None:
            raise ValueError('Configure explícitamente la fiscalidad de los honorarios históricos.')
        operation = operation_dates.get(row['key'])
        snap = fiscal_snapshot(terms, config, row, date.fromisoformat(row['date']),
            operation_date=date.fromisoformat(operation) if operation else None)
        snap.update(source_key=row['key'], management_percentage=row['fee_percentage'])
        return snap

    def preview(self, db, start, end, property_ids, assignments=None, operation_dates=None):
        assignments, operation_dates = dict(assignments or {}), dict(operation_dates or {})
        catalog = self.catalog(db, start, end, property_ids)
        ids = sorted(set(map(int, property_ids)))
        if not ids or len(catalog) != len(ids):
            raise ValueError('Seleccione fincas existentes.')
        owners = sorted({o['owner_id'] for p in catalog for o in p['owners'] if o['has_movements']})
        errors = [e for p in catalog for e in p['errors']]
        views, issues, date_requests = [], [], []
        for owner_id in owners:
            raw = self.legacy.preview(db, owner_id, start, end, ids)
            errors.extend(raw['errors'])
            rows = [deepcopy(r) for r in raw['rows'] if r['kind'] != 'prior_balance']
            resolved, fallback_signatures = [], {}
            for row in rows:
                row['owner_id'] = owner_id
                try:
                    snap = self._fiscal(db, row, operation_dates) if row['kind'] == 'income' else None
                    if snap:
                        row['fiscal_snapshot'] = snap
                        row['distribution'][str(owner_id)]['fiscal_snapshot'] = snap
                    resolved.append(row)
                except ValueError as exc:
                    errors.append(f"{row['key']}: {exc}")
                    if 'fecha fiscal de operación' in str(exc):
                        date_requests.append(dict(key=row['key'],concept=row['concept'],receipt_date=row['date']))
            income_properties = {r['property_id'] for r in resolved if r.get('fiscal_snapshot')}
            for row in resolved:
                # Resolve configuration only; grouping/assignment lives in the
                # common pure planner, including expense-only properties.
                if row['property_id'] not in income_properties and row['property_id'] not in fallback_signatures:
                    try:
                        terms = self.legacy.fee_terms(db, row['property_id'], owner_id, start, end)
                        cfg = db.scalar(select(FeeTaxConfiguration).where(FeeTaxConfiguration.terms_id == terms.id))
                        fallback_signatures[row['property_id']] = fee_signature(terms, cfg.configuration if cfg else None)
                    except ValueError as exc:
                        errors.append(f"{row['key']}: {exc}")
            try:
                planned = group_fee_sources(owner_id, resolved,
                    {key.split('|', 1)[1]: value for key, value in assignments.items()
                     if key.startswith(f'{owner_id}|') and key.split('|', 1)[1] in {r['key'] for r in resolved}},
                    property_signatures=fallback_signatures)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            signatures = {g['group_key']: g['signature'] for g in planned['groups']}
            by_key = {r['key']: r for r in resolved}
            for issue in planned['issues']:
                if not issue['candidates']:
                    errors.append(issue['message'])
                else:
                    issues.append(dict(field=f"{owner_id}|{issue['source_key']}",
                        source=by_key[issue['source_key']], candidates=[dict(key=k,
                        label=self._group_label(signatures[k]['fields'])) for k in issue['candidates']]))
            state = self._state(db, owner_id)
            for planned_group in planned['groups']:
                digest = planned_group['group_key']
                group = dict(rows=planned_group['sources'], signature=planned_group['signature'])
                view = self._plan(db, owner_id, start, end, group, state)
                view.update(group_key=digest, fee_signature=group['signature'], property_ids=planned_group['property_ids'],
                            selected_properties=ids, assignments=assignments, operation_dates=operation_dates)
                view['fingerprint'] = fingerprint(view)
                views.append(dict(name=db.get(Owner, owner_id).name, view=view))
        return dict(start=str(start), end=str(end), property_ids=ids, groups=catalog, individuals=views,
            issues=issues, date_requests=date_requests, errors=list(dict.fromkeys(errors)), assignments=assignments, operation_dates=operation_dates,
            fingerprint=fingerprint([str(start), str(end), ids, [v['view']['fingerprint'] for v in views], issues, errors]))

    @staticmethod
    def _group_label(fields):
        return (f"Honorarios {fields['percentage']} % · {TREATMENTS[fields['tax_treatment']]} · "
                f"IVA {fields['vat_rate']} % · Retención {fields['withholding_rate']} %")

    def _plan(self, db, owner, start, end, group, state):
        before = deepcopy(state)
        rows, corrections, funds, new = group['rows'], [], [], []
        for row in rows:
            obligations = []
            if row['kind'] == 'expense':
                obligations = [('expense_advance', D(row['manager']), 'expense')]
            else:
                obligations = [('management_fee', D(row.get('fee', '0')), 'fee')]
                if D(row['manager']) > 0:
                    funds.append(dict(source_key=row['key'], amount=row['manager'], date=row['date']))
                elif D(row['manager']) < 0:
                    obligations.append(('other_adjustment', -D(row['manager']), 'return'))
            for kind, amount, suffix in obligations:
                key = f"{row['key']}:{suffix}"
                if amount > 0:
                    item = dict(key=key, kind=kind, date=row['date'], generated=str(amount), compensated='0.00')
                    state[key] = item
                    new.append({**item, 'source_key': row['key']})
                elif amount < 0:
                    original = f"{row.get('reversal_of')}:{suffix}"
                    if original not in state:
                        # A receipt and its refund selected together: the positive
                        # source must precede its correction.
                        raise ValueError('Falta la obligación original de la corrección; revise el histórico.')
                    item = state[original]
                    if D(item['generated']) + amount < 0:
                        raise ValueError('La corrección excede la obligación original.')
                    generated = D(item['generated']) + amount
                    release = max(ZERO, D(item['compensated']) - generated)
                    item.update(generated=str(generated), compensated=str(D(item['compensated']) - release))
                    corrections.append(dict(key=original, source_key=row['key'], amount=str(amount), release=str(release)))
                    if release:
                        funds.append(dict(source_key=row['key'], amount=str(release), date=row['date']))
        current_funds = sum((D(f['amount']) for f in funds), ZERO)
        obligations = [Obligation(k, owner, r['kind'], date.fromisoformat(r['date']),
                                 D(r['generated']), D(r['compensated'])) for k,r in state.items()]
        plan = compensation_plan(owner, current_funds, obligations)
        previous_used = ZERO
        for application in plan['applications']:
            key = application['obligation_key']
            if key in before:
                previous_used += D(application['amount'])
            state[key]['compensated'] = str(D(state[key]['compensated']) + D(application['amount']))
        def total(kind, field):
            return sum((D(r.get(field, '0')) for r in rows if r['kind'] == kind), ZERO)
        income, expenses, fees = total('income','amount'), total('expense','amount'), total('income','fee')
        period = income - expenses - fees
        pending_fee = sum((D(r['generated']) - D(r['compensated']) for r in state.values() if r['kind']=='management_fee'), ZERO)
        pending_expense = sum((D(r['generated']) - D(r['compensated']) for r in state.values() if r['kind']=='expense_advance'), ZERO)
        return dict(owner_id=owner, start=str(start), end=str(end), rows=rows, errors=[], billing=True,
            obligations_before=[before[k] for k in sorted(before)], new_obligations=new, corrections=corrections,
            funds=funds, applications=plan['applications'], obligations_after=[deepcopy(state[k]) for k in sorted(state)],
            totals=dict(income=str(income), expenses=str(expenses), fees=str(fees), period_balance=str(period),
                economic_balance=str(period-previous_used), prior_balance=str(-previous_used),
                funds_balance=str(total('income','manager')-total('expense','manager')-fees-previous_used),
                payout_due=plan['available'], carry_forward=str(-D(plan['pending'])), manager_credit=plan['pending'],
                pending_fee=str(pending_fee), pending_expense=str(pending_expense),
                directly_received=str(total('income','direct')), manager_held_funds=str(total('income','manager')),
                inter_owner_difference=str(total('income','difference'))))

    def save_drafts(self, db, start, end, properties, expected, request_key, assignments=None, operation_dates=None):
        require_synthetic_invoicing(db)
        key = request_id(request_key)
        with financial_transaction(db):
            old = [s for s in db.scalars(select(OwnerSettlement)) if s.selection.get('selection_request') == key]
            if old:
                if any(s.selection['selection_fingerprint'] != expected for s in old):
                    raise ValueError('Solicitud ya utilizada con otros datos.')
                return old
            batch = self.preview(db, start, end, properties, assignments, operation_dates)
            if expected != batch['fingerprint'] or batch['errors'] or batch['issues'] or not batch['individuals']:
                raise ValueError('Revise cambios o gastos sin asignar antes de guardar.')
            result = []
            for entry in batch['individuals']:
                view = entry['view']
                item = OwnerSettlement(owner_id=view['owner_id'], period_start=start, period_end=end, status='draft',
                    selection=dict(billing=True, properties=properties, group_key=view['group_key'],
                        assignments=assignments or {}, operation_dates=operation_dates or {}, selection_request=key,
                        selection_fingerprint=expected), snapshot=view, fingerprint=view['fingerprint'],
                    request_key=str(uuid5(UUID(key), f"{view['owner_id']}:{view['group_key']}")))
                db.add(item); result.append(item)
        return result

    def close(self, db, settlement_id, expected):
        require_synthetic_invoicing(db)
        with financial_transaction(db):
            item = db.get(OwnerSettlement, settlement_id)
            if not item or item.fingerprint != expected:
                raise ValueError('Versión de liquidación no válida.')
            if item.status == 'closed':
                return item
            if item.status != 'draft':
                raise ValueError('La liquidación no está en borrador.')
            selection = item.selection
            batch = self.preview(db, item.period_start, item.period_end, selection['properties'],
                                 selection['assignments'], selection['operation_dates'])
            view = next((e['view'] for e in batch['individuals'] if e['view']['owner_id']==item.owner_id
                         and e['view']['group_key']==selection['group_key']), None)
            if batch['errors'] or batch['issues'] or not view or view['fingerprint'] != expected:
                raise ValueError('Datos desactualizados: otro cierre o cambio ha alterado la compensación. Revise nuevamente.')
            actual_state=self._state(db,item.owner_id)
            if [actual_state[k] for k in sorted(actual_state)] != view['obligations_before']:
                # Preview simulates earlier groups. They must really be closed
                # before a later group may consume their residual balances.
                raise ValueError('Datos desactualizados: cierre primero las liquidaciones anteriores del orden propuesto y revise.')
            lines = {}
            for row in view['rows']:
                line = OwnerSettlementLine(settlement_id=item.id, owner_id=item.owner_id,
                    kind=row['kind'], source_key=row['key'], property_id=row['property_id'], amount=D(row['amount']),
                    fee_amount=D(row.get('fee','0')), ownership_id=row.get('ownership_id'), fee_terms_id=row.get('fee_terms_id'),
                    snapshot=row, **{('payment_allocation_id' if row['kind']=='income' else 'expense_payment_id'):row['source_id']})
                db.add(line); db.flush(); lines[row['key']] = line
            for row in view['new_obligations']:
                db.add(FeeObligation(owner_id=item.owner_id, settlement_id=item.id,
                    source_line_id=lines[row['source_key']].id, source_key=row['key'], kind=row['kind'],
                    effective_date=date.fromisoformat(row['date']), amount=D(row['generated']), snapshot=row))
            db.flush()
            obligations = {o.source_key:o for o in db.scalars(select(FeeObligation).where(FeeObligation.owner_id==item.owner_id))}
            for correction in view['corrections']:
                obligation = obligations[correction['key']]
                db.add(FeeObligationAdjustment(obligation_id=obligation.id, settlement_id=item.id,
                    source_key=f"{item.owner_id}:{correction['source_key']}:{obligation.id}",
                    effective_date=date.fromisoformat(lines[correction['source_key']].snapshot['date']),
                    amount=D(correction['amount']), reason='Corrección por devolución de la fuente original'))
                remaining = D(correction['release'])
                apps = list(db.scalars(select(FeeCompensation).where(FeeCompensation.obligation_id==obligation.id,
                    FeeCompensation.direction=='application').order_by(FeeCompensation.id.desc())))
                for app in apps:
                    reversed_amount = sum(db.scalars(select(FeeCompensation.amount).where(FeeCompensation.corrects_id==app.id)), ZERO)
                    amount = min(remaining, app.amount-reversed_amount)
                    if amount:
                        db.add(FeeCompensation(obligation_id=obligation.id, fund_id=app.fund_id, settlement_id=item.id,
                            effective_date=item.period_end, amount=amount, direction='reversal', corrects_id=app.id,
                            request_key=f"close:{item.id}:reverse:{app.id}", reason='Devolución posterior'))
                        remaining -= amount
                if remaining:
                    raise ValueError('No se ha podido trazar la reversión completa.')
                invoice_id = db.scalar(select(ManagementFeeInvoice.id).join(ManagementFeeInvoiceLine,
                    ManagementFeeInvoiceLine.invoice_id==ManagementFeeInvoice.id).join(ManagementFeeInvoiceSource,
                    ManagementFeeInvoiceSource.line_id==ManagementFeeInvoiceLine.id).where(
                    ManagementFeeInvoiceSource.source_id==obligation.source_line_id, ManagementFeeInvoice.status=='issued'))
                if invoice_id:
                    db.add(InvoiceRectificationNotice(invoice_id=invoice_id,
                        source_line_id=lines[correction['source_key']].id, reason='Devolución de honorarios ya facturados'))
            fund_rows = []
            for source in sorted({f['source_key'] for f in view['funds']}):
                amount = sum((D(f['amount']) for f in view['funds'] if f['source_key']==source), ZERO)
                row = FeeFund(owner_id=item.owner_id, settlement_id=item.id, source_line_id=lines[source].id,
                              effective_date=date.fromisoformat(lines[source].snapshot['date']), amount=amount)
                db.add(row); db.flush(); fund_rows.append([row,amount])
            n = 0
            for application in view['applications']:
                remaining = D(application['amount'])
                for fund in fund_rows:
                    amount = min(remaining, fund[1])
                    if amount:
                        n += 1
                        db.add(FeeCompensation(obligation_id=obligations[application['obligation_key']].id,
                            fund_id=fund[0].id, settlement_id=item.id, effective_date=item.period_end,
                            amount=amount, direction='application', request_key=f'close:{item.id}:apply:{n}'))
                        remaining -= amount; fund[1] -= amount
                if remaining:
                    raise ValueError('Fondos insuficientes tras revalidar.')
            from backend.services.settlement_document_service import document_identity
            view['document_identity'] = document_identity(db, item, view['rows'])
            item.status, item.closed_at, item.snapshot = 'closed', now(), view
        return item
