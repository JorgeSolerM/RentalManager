"""Review-only impact inspection and one atomic, conservative date change."""
import calendar
import hashlib
import json
from datetime import date, datetime, timezone
from uuid import UUID
from sqlalchemy import select, inspect, table, column
from backend.core.business_time import business_today
from backend.core.early_termination import economic_end_exclusive
from backend.models.booking import Booking
from backend.models.booking_early_termination import BookingEarlyTermination, BookingEarlyTerminationSourceState
from backend.models.booking_charge import BookingCharge
from backend.models.booking_financial_terms import BookingFinancialTerms
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.booking_sepa_mandate import BookingSepaMandate
from backend.models.sepa_collection import SepaDebit, SepaBatch, SepaBatchGroup, SepaDebitChargeAllocation, SepaExportArtifact
from backend.models.owner_settlement import OwnerSettlementLine, OwnerSettlement
from backend.services.financial_transaction import financial_transaction
from backend.services.financial_service import FinancialService


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def columns(row, names):
    return {name: getattr(row, name) for name in names.split()}


def related_invoice_summaries(db, settlement_ids):
    """Read optional invoice impact without requiring the pending billing module.

    No invoice table means this deployment has no billing schema yet. If it is
    present, query errors are not hidden: an incompatible schema must fail closed.
    """
    if not settlement_ids or not inspect(db.connection()).has_table('management_fee_invoices'):
        return []
    invoices = table('management_fee_invoices', column('id'), column('settlement_id'), column('status'))
    rows = db.execute(select(invoices.c.id, invoices.c.status).where(
        invoices.c.settlement_id.in_(settlement_ids)).order_by(invoices.c.id)).mappings()
    return [dict(row) for row in rows]


def protect_imported_dates(db, booking, source_start, source_end, seen_at=None):
    """Keep local administrative dates; expose latest source dates as a conflict."""
    termination = booking.early_termination
    if not termination:
        return False
    state = db.scalar(select(BookingEarlyTerminationSourceState).where(
        BookingEarlyTerminationSourceState.termination_id == termination.id))
    if state is None:
        state = BookingEarlyTerminationSourceState(termination_id=termination.id)
        db.add(state)
    state.source_check_in = source_start
    state.source_check_out = source_end
    state.seen_at = seen_at or datetime.now(timezone.utc).replace(tzinfo=None)
    return source_start != booking.check_in or source_end != booking.check_out


class BookingEarlyTerminationService:
    def preview(self, db, booking_id, effective_departure, economic_last_day, *, reason='', notes='', accept_proration=False):
        booking = db.get(Booking, booking_id)
        if not booking:
            raise ValueError('Reserva no encontrada.')
        if booking.early_termination:
            raise ValueError('Esta reserva ya tiene una finalización anticipada registrada. Su historial no se reemplaza.')
        today = business_today()
        if not booking.check_in <= today < booking.check_out:
            raise ValueError('La acción corresponde a reservas ya iniciadas cuyo fin contratado aún no ha llegado.')
        if not booking.check_in < effective_departure < booking.check_out:
            raise ValueError('La salida efectiva debe ser posterior a la entrada y anterior a la salida contratada.')
        if not booking.check_in <= economic_last_day < booking.check_out:
            raise ValueError('El último día a cargo debe estar dentro del contrato original; esta acción no amplía obligaciones.')
        reason, notes = str(reason or '').strip(), str(notes or '').strip()
        if len(reason) > 500 or len(notes) > 4000:
            raise ValueError('Motivo u observaciones demasiado largos.')
        limit = economic_end_exclusive(economic_last_day)
        charges = list(db.scalars(select(BookingCharge).where(BookingCharge.booking_id == booking_id).order_by(BookingCharge.id)))
        payments = list(db.scalars(select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.id)))
        charge_ids, payment_ids = [c.id for c in charges], [p.id for p in payments]
        allocations = list(db.scalars(select(PaymentAllocation).where(
            (PaymentAllocation.charge_id.in_(charge_ids)) | (PaymentAllocation.payment_id.in_(payment_ids))).order_by(PaymentAllocation.id)))
        terms = list(db.scalars(select(BookingFinancialTerms).where(BookingFinancialTerms.booking_id == booking_id).order_by(BookingFinancialTerms.id)))
        debits = list(db.scalars(select(SepaDebit).where(SepaDebit.booking_id == booking_id).order_by(SepaDebit.id)))
        debit_ids = [d.id for d in debits]
        debit_allocations = list(db.scalars(select(SepaDebitChargeAllocation).where(SepaDebitChargeAllocation.debit_id.in_(debit_ids)).order_by(SepaDebitChargeAllocation.id)))
        links = list(db.scalars(select(BookingSepaMandate).where(BookingSepaMandate.booking_id == booking_id).order_by(BookingSepaMandate.id)))
        groups = list(db.scalars(select(SepaBatchGroup).where(SepaBatchGroup.id.in_([d.group_id for d in debits])).order_by(SepaBatchGroup.id)))
        batches = list(db.scalars(select(SepaBatch).where(SepaBatch.id.in_([g.batch_id for g in groups])).order_by(SepaBatch.id)))
        artifacts = list(db.scalars(select(SepaExportArtifact).where(SepaExportArtifact.group_id.in_([g.id for g in groups])).order_by(SepaExportArtifact.id)))
        settlement_lines = list(db.scalars(select(OwnerSettlementLine).where(OwnerSettlementLine.payment_allocation_id.in_([a.id for a in allocations])).order_by(OwnerSettlementLine.id)))
        settlements = list(db.scalars(select(OwnerSettlement).where(OwnerSettlement.id.in_([l.settlement_id for l in settlement_lines])).order_by(OwnerSettlement.id)))
        invoices = related_invoice_summaries(db, [s.id for s in settlements])
        nearby = list(db.scalars(select(Booking).where(Booking.room_id == booking.room_id, Booking.id != booking.id,
            Booking.check_in < booking.check_out, Booking.check_out > booking.check_in).order_by(Booking.check_in, Booking.id)))
        conflicts = [b.id for b in nearby if b.check_in < effective_departure and b.check_out > booking.check_in]
        affected = []
        charge_rows = []
        balance_service = FinancialService()
        for c in charges:
            # A deposit is independent of duration. Undated other obligations
            # after the cutoff are deliberately not guessed to be independent.
            incompatible = c.lifecycle != 'void' and c.type not in {'security_deposit', 'reservation_deposit', 'deposit_retention'} and (
                (c.service_period_end is not None and c.service_period_end > limit) or
                (c.service_period_start is not None and c.service_period_start >= limit) or
                (c.service_period_start is None and c.due_date >= limit))
            if incompatible:
                affected.append(c.id)
            allocated = [a for a in allocations if a.charge_id == c.id]
            paid = sum((a.amount * (1 if p.direction == 'receipt' else -1) for a in allocated for p in payments if p.id == a.payment_id and p.lifecycle == 'posted'), 0)
            state = 'Borrador' if c.lifecycle == 'draft' else 'Anulado' if c.lifecycle == 'void' else 'Cobrado' if paid >= c.amount else 'Parcialmente cobrado' if paid > 0 else 'Contabilizado pendiente'
            charge_rows.append({**columns(c, 'id type concept lifecycle amount due_date service_period_start service_period_end'), 'state': state, 'affected': incompatible})
        affected_debits = [d.id for d in debits if d.status != 'cancelled' and any(a.debit_id == d.id and a.charge_id in affected for a in debit_allocations)]
        blockers = []
        if conflicts:
            blockers.append('Hay reservas que siguen solapadas con el intervalo resultante. Revise los conflictos antes de confirmar.')
        if affected:
            blockers.append('Existen cargos posteriores o que atraviesan el fin económico. Resuélvalos expresamente desde Cuenta económica y repita la revisión. No se anulan ni recalculan aquí.')
        if affected_debits:
            blockers.append('Hay adeudos SEPA afectados. Cambiar la reserva no cancela órdenes bancarias; revise la remesa y su estado antes de continuar.')
        partial_month = economic_last_day.day != calendar.monthrange(economic_last_day.year, economic_last_day.month)[1]
        if partial_month and not accept_proration:
            blockers.append('Revise y acepte expresamente el prorrateo existente por días naturales reales del último mes.')
        request = dict(effective_departure=effective_departure.isoformat(), economic_last_day=economic_last_day.isoformat(), reason=reason, notes=notes, accept_proration=bool(accept_proration))
        snapshot = dict(booking=columns(booking, 'id room_id room_calendar_id origin external_reference ical_uid check_in check_out expected_arrival_date expected_departure_date price source_guest_name notes'),
            charges=[columns(c, 'id type direction lifecycle amount currency due_date service_period_start service_period_end generation_key financial_terms_id') for c in charges],
            payments=[columns(p, 'id amount lifecycle direction effective_date') for p in payments],
            allocations=[columns(a, 'id payment_id charge_id amount') for a in allocations],
            terms=[columns(t, 'id version status monthly_rent effective_from effective_until usual_due_day deposit_agreed') for t in terms],
            debits=[columns(d, 'id group_id status amount payment_id return_payment_id') for d in debits],
            debit_allocations=[columns(a, 'id debit_id charge_id amount reserved') for a in debit_allocations],
            batches=[columns(b, 'id status requested_collection_date') for b in batches],
            artifacts=[columns(a, 'id sha256') for a in artifacts],
            mandates=[columns(m, 'id mandate_id active') for m in links],
            settlements=[columns(s, 'id status') for s in settlements],
            invoices=invoices,
            nearby=[columns(b, 'id check_in check_out') for b in nearby], request=request, today=today.isoformat())
        plan = []
        confirmed = [t for t in terms if t.status == 'confirmed']
        if len(confirmed) == 1:
            plan = balance_service.preview_monthly_rent(check_in=booking.check_in, check_out=limit,
                monthly_rent=confirmed[0].monthly_rent, usual_due_day=confirmed[0].usual_due_day, terms_id=confirmed[0].id)
        elif len(confirmed) > 1:
            blockers.append('Existen varias versiones de renta. Revisión económica necesaria; no se infiere un nuevo plan.')
        return dict(booking=booking, request=request, snapshot=snapshot, fingerprint=digest(snapshot), blockers=blockers,
            charges=charge_rows, payments=snapshot['payments'], debits=snapshot['debits'], batches=snapshot['batches'],
            mandates=snapshot['mandates'], settlements=snapshot['settlements'], invoices=snapshot['invoices'],
            affected_charges=affected, affected_debits=affected_debits, conflicts=conflicts, nearby=snapshot['nearby'],
            released_days=(booking.check_out-effective_departure).days, partial_month=partial_month, plan=plan,
            original_departure=booking.check_out, economic_end=limit)

    def confirm(self, db, booking_id, effective_departure, economic_last_day, *, expected, request_key, reason='', notes='', accept_proration=False):
        try:
            request_key = str(UUID(request_key))
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Identificador de operación inválido.') from None
        request = dict(effective_departure=effective_departure.isoformat(), economic_last_day=economic_last_day.isoformat(),
            reason=str(reason or '').strip(), notes=str(notes or '').strip(), accept_proration=bool(accept_proration))
        with financial_transaction(db):
            prior = db.scalar(select(BookingEarlyTermination).where((BookingEarlyTermination.booking_id == booking_id) | (BookingEarlyTermination.request_key == request_key)))
            if prior:
                if prior.booking_id == booking_id and prior.request_key == request_key and prior.snapshot['request'] == request:
                    return prior
                raise ValueError('Ya existe una operación para esta reserva o identificador. Recargue el historial; no se ha duplicado.')
            view = self.preview(db, booking_id, effective_departure, economic_last_day, reason=reason, notes=notes, accept_proration=accept_proration)
            if expected != view['fingerprint']:
                raise ValueError('Los datos han cambiado desde la revisión. Revise de nuevo antes de confirmar.')
            if view['blockers']:
                raise ValueError(' '.join(view['blockers']))
            booking = view['booking']
            record = BookingEarlyTermination(booking_id=booking.id, request_key=request_key, original_check_in=booking.check_in,
                original_check_out=booking.check_out, effective_departure=effective_departure, economic_last_day=economic_last_day,
                reason=request['reason'] or None, notes=request['notes'] or None, actor=None,
                snapshot=json.loads(json.dumps(view['snapshot'], default=str)))
            booking.check_out = effective_departure
            booking.expected_departure_date = effective_departure
            db.flush()
            db.add(record)
            db.flush()
        return record
