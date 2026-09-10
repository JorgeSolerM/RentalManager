from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4
from types import SimpleNamespace

from sqlalchemy import select, text
from sqlalchemy.orm import joinedload, selectinload

from backend.core.bbva_sepa import render_bbva, sepa_text, validate_bank_data
from backend.core.business_time import business_today
from backend.core.iban import mask_iban
from backend.models.booking import Booking
from backend.models.booking_charge import BookingCharge
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.room import Room
from backend.models.sepa_collection import SepaSettings, SepaBatch, SepaBatchGroup, SepaDebit, SepaDebitChargeAllocation, SepaExportArtifact
from backend.repositories.sepa_repository import SepaRepository
from backend.services.financial_service import FinancialService
from backend.services.financial_transaction import financial_transaction

PRIVATE_STORAGE = Path(__file__).resolve().parents[2] / "data/finance/sepa"
ALLOWED_TYPES = {"rent", "security_deposit", "utilities", "extraordinary"}


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@contextmanager
def atomic(db):
    """Serialize SQLite collection writers before reading mutable balances.

    A unique charge reservation + payment link are the final integrity guards.
    No financial-service method committing independently is called in this unit.
    """
    with financial_transaction(db):
        db.execute(text("INSERT INTO sepa_settings (id) VALUES (1) ON CONFLICT(id) DO UPDATE SET id=1"))
        yield


class SepaCollectionService:
    def __init__(self, storage=PRIVATE_STORAGE):
        self.storage = Path(storage)
        self.sepa = SepaRepository()
        self.finance = FinancialService()

    def settings(self, db):
        return db.get(SepaSettings, 1)

    def save_settings(self, db, name, identifier):
        name = sepa_text(name, 70)
        identifier = sepa_text(identifier, 35)
        with atomic(db):
            settings = db.get(SepaSettings, 1)
            settings.initiator_name = name
            settings.initiator_identifier = identifier

    def list_batches(self, db):
        return list(db.scalars(select(SepaBatch).options(selectinload(SepaBatch.groups).selectinload(SepaBatchGroup.debits)).order_by(SepaBatch.id.desc())))

    def get_batch(self, db, batch_id):
        batch = db.scalar(select(SepaBatch).where(SepaBatch.id == batch_id).options(
            selectinload(SepaBatch.groups).selectinload(SepaBatchGroup.debits).selectinload(SepaDebit.allocations),
            selectinload(SepaBatch.groups).joinedload(SepaBatchGroup.artifact),
            selectinload(SepaBatch.groups).selectinload(SepaBatchGroup.debits).joinedload(SepaDebit.payment),
        ))
        if not batch:
            raise ValueError("Remesa no encontrada.")
        return batch

    def resolve(self, db, booking, collection_date):
        ownerships = [o for o in booking.room.property.ownerships if o.active
                      and (o.effective_from is None or o.effective_from <= collection_date)
                      and (o.effective_until is None or o.effective_until >= collection_date)]
        accounts = {o.rent_bank_account_id for o in ownerships if o.rent_bank_account and o.rent_bank_account.active and o.rent_bank_account.receives_rent}
        if not accounts:
            raise ValueError("Falta cuenta receptora")
        profiles = [p for p in self.sepa.compatible_profiles(db, booking) if p.bank_account_id in accounts]
        if not profiles:
            raise ValueError("Falta acreedor")
        binding = booking.active_sepa_mandate_link
        if len(profiles) > 1:
            # An explicitly chosen binding disambiguates; never guess an owner.
            profiles = [p for p in profiles if binding and p.id == binding.mandate.creditor_profile_id]
            if len(profiles) != 1:
                raise ValueError("Acreedor ambiguo")
        profile = profiles[0]
        if not binding:
            raise ValueError("Falta mandato")
        mandate = binding.mandate
        if mandate.status != "active" or (mandate.active_from and mandate.active_from > collection_date):
            raise ValueError("Mandato inactivo")
        if mandate.creditor_profile_id != profile.id:
            raise ValueError("El mandato no corresponde al acreedor")
        if not mandate.signature_date or mandate.signature_date > collection_date:
            raise ValueError("Fecha de firma del mandato no válida")
        if mandate.amendment_indicator:
            raise ValueError("Mandato modificado: requiere datos de modificación no soportados todavía")
        if not mandate.mandate_reference or len(mandate.mandate_reference) > 35 or sepa_text(mandate.mandate_reference, 35) != mandate.mandate_reference:
            raise ValueError("Referencia del mandato no compatible con el perfil bancario")
        if profile.scheme != "CORE" or profile.bank_account.currency != "EUR":
            raise ValueError("Se requiere cuenta EUR y esquema CORE")
        creditor = {"creditor_name": profile.creditor_name, "creditor_identifier": profile.creditor_identifier,
                    "creditor_iban": profile.bank_account.iban, "creditor_bic": profile.bank_account.bic}
        debtor = {"debtor_name": mandate.debtor_name, "debtor_iban": mandate.debtor_iban,
                  "debtor_bic": mandate.debtor_bic, "mandate_reference": mandate.mandate_reference,
                  "signature_date": mandate.signature_date.isoformat(), "sequence": mandate.mandate_type}
        validate_bank_data(creditor)
        validate_bank_data(debtor)
        return profile, mandate, creditor, debtor

    def preview(self, db, period, property_ids, collection_date):
        if period.day != 1 or not property_ids:
            raise ValueError("Seleccione un mes y al menos una finca.")
        end = date(period.year + (period.month == 12), period.month % 12 + 1, 1)
        charges = list(db.scalars(select(BookingCharge).join(Booking).join(Room).where(
            Room.property_id.in_(set(property_ids)), BookingCharge.due_date >= period, BookingCharge.due_date < end,
            BookingCharge.lifecycle == "posted", BookingCharge.direction == "debit", BookingCharge.type.in_(ALLOWED_TYPES),
        ).order_by(Room.property_id, BookingCharge.booking_id, BookingCharge.due_date, BookingCharge.id)))
        reserved = set(db.scalars(select(SepaDebitChargeAllocation.charge_id).where(SepaDebitChargeAllocation.reserved.is_(True))))
        used_once = set(db.scalars(select(SepaDebit.mandate_id).distinct()))
        bookings = {}
        rows = []
        for charge in charges:
            balance = self.finance.charge_balance(db, charge.id).outstanding_amount
            if balance <= 0:
                continue
            booking = bookings.setdefault(charge.booking_id, None)
            if booking is None:
                booking = bookings[charge.booking_id] = self.sepa.get_booking(db, charge.booking_id)
            row = dict(charge=charge, booking=booking, amount=balance, eligible=False,
                       reason="Listo", profile=None, mandate=None, masked_iban="", creditor=None, debtor=None)
            try:
                if charge.currency != "EUR":
                    raise ValueError("El cargo no está en EUR")
                if charge.id in reserved:
                    raise ValueError("Cargo ya incluido en otra remesa")
                profile, mandate, creditor, debtor = self.resolve(db, booking, collection_date)
                row.update(profile=profile, mandate=mandate, masked_iban=mask_iban(mandate.debtor_iban), creditor=creditor, debtor=debtor)
                if mandate.mandate_type == "OOFF" and (mandate.last_used_at or mandate.id in used_once):
                    raise ValueError("Mandato de un solo uso ya utilizado")
                row["eligible"] = True
            except ValueError as error:
                row["reason"] = str(error)
            rows.append(row)
        return rows

    @staticmethod
    def administrative_name(value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError('Nombre de remesa no válido.')
        value = value.strip()
        if len(value) > 160 or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError('El nombre admite hasta 160 caracteres, sin caracteres de control.')
        return value or None

    def rename(self, db, batch_id, name):
        from backend.services.financial_transaction import financial_transaction
        name = self.administrative_name(name)
        with financial_transaction(db):
            batch = db.get(SepaBatch, batch_id)
            if batch is None:
                raise ValueError('Remesa no encontrada.')
            batch.name = name

    def create(self, db, period, property_ids, collection_date, charge_ids, request_key, *, name=None):
        name = self.administrative_name(name)
        request_key = str(UUID(request_key))
        if collection_date < business_today():
            raise ValueError("La fecha solicitada de cobro está en el pasado.")
        if not charge_ids or len(charge_ids) != len(set(charge_ids)):
            raise ValueError("Seleccione cargos sin duplicados.")
        with atomic(db):
            previous = db.scalar(select(SepaBatch).where(SepaBatch.request_key == request_key))
            if previous:
                previous = self.get_batch(db, previous.id)
                original_ids = {a.charge_id for g in previous.groups for d in g.debits for a in d.allocations}
                if original_ids != set(charge_ids) or previous.period != period or previous.requested_collection_date != collection_date:
                    raise ValueError("La solicitud ya fue utilizada con otra selección.")
                return previous
            settings = self.settings(db)
            initiator = {"initiator_name": sepa_text(settings.initiator_name, 70), "initiator_identifier": sepa_text(settings.initiator_identifier, 35)}
            rows = {r["charge"].id: r for r in self.preview(db, period, property_ids, collection_date)}
            if any(i not in rows or not rows[i]["eligible"] for i in charge_ids):
                raise ValueError("La selección ha cambiado o contiene cargos no elegibles. Revise la previsualización.")
            batch = SepaBatch(reference="RM" + uuid4().hex, name=name, request_key=request_key, period=period, requested_collection_date=collection_date)
            db.add(batch)
            db.flush()
            groups, grouped_rows, single_use = {}, {}, {}
            for i in sorted(charge_ids):
                row = rows[i]
                profile, mandate, booking = row["profile"], row["mandate"], row["booking"]
                if mandate.mandate_type == "OOFF":
                    if mandate.id in single_use and single_use[mandate.id] != booking.id:
                        raise ValueError("Un mandato OOFF no puede generar varios adeudos.")
                    single_use[mandate.id] = booking.id
                if profile.id not in groups:
                    groups[profile.id] = SepaBatchGroup(batch_id=batch.id, creditor_profile_id=profile.id,
                        bank_account_id=profile.bank_account_id, snapshot={**initiator, **row["creditor"]})
                    db.add(groups[profile.id]); db.flush()
                key = (profile.id, booking.id, mandate.id)
                grouped_rows.setdefault(key, []).append(row)
            for (profile_id, booking_id, mandate_id), members in grouped_rows.items():
                row = members[0]
                booking = row["booking"]
                breakdown = [{"id": r["charge"].id, "concept": r["charge"].concept, "amount": str(r["amount"])} for r in members]
                location = sepa_text(f"{booking.room.property.name} - {booking.room.code}", 60, truncate=True)
                concepts = sepa_text(" + ".join(c["concept"] for c in breakdown), 137 - len(location), truncate=True)
                # Only an explicit new batch can retry returned charges. Link the
                # latest returned instruction; never revive the old EndToEndId.
                previous = list(db.scalars(select(SepaDebit).join(SepaDebitChargeAllocation)
                    .where(SepaDebitChargeAllocation.charge_id.in_([r['charge'].id for r in members]),
                           SepaDebit.booking_id==booking_id, SepaDebit.mandate_id==mandate_id,
                           SepaDebit.status=='returned').order_by(SepaDebit.id.desc())))
                debit = SepaDebit(group_id=groups[profile_id].id, booking_id=booking_id, mandate_id=mandate_id,
                    creditor_profile_id=profile_id, amount=sum(r["amount"] for r in members), requested_collection_date=collection_date,
                    end_to_end_id="RM" + uuid4().hex, remittance_information=f"{concepts} - {location}",
                    retry_of_id=previous[0].id if previous else None,
                    snapshot={**row["debtor"], "property": booking.room.property.name, "room": booking.room.code,
                              "person": booking.operational_person_name, "charges": breakdown})
                db.add(debit)
                db.flush()
                for member in members:
                    db.add(SepaDebitChargeAllocation(debit_id=debit.id, charge_id=member["charge"].id, amount=member["amount"]))
            db.flush()
        return batch

    def _validate_debit(self, db, debit, *, bank=False):
        for allocation in debit.allocations:
            charge = db.get(BookingCharge, allocation.charge_id)
            balance = self.finance.charge_balance(db, allocation.charge_id)
            if charge.lifecycle != "posted" or charge.booking_id != debit.booking_id or charge.currency != "EUR" or balance.outstanding_amount < allocation.amount:
                raise ValueError("Un cargo ha cambiado o ya no tiene saldo suficiente: puede haberse pagado por otro medio. Se bloquea el doble cobro; no se ha creado ningún Payment SEPA.")
        if sum(a.amount for a in debit.allocations) != debit.amount:
            raise ValueError("Desglose del adeudo incoherente.")
        if bank:
            booking = self.sepa.get_booking(db, debit.booking_id)
            profile, mandate, creditor, debtor = self.resolve(db, booking, debit.requested_collection_date)
            if profile.id != debit.creditor_profile_id or mandate.id != debit.mandate_id or any(debit.snapshot[k] != v for k, v in debtor.items()) or any(debit.group.snapshot[k] != v for k, v in creditor.items()):
                raise ValueError("Los datos bancarios han cambiado desde la preparación de la remesa.")

    def export(self, db, batch_id):
        created_files = []
        try:
            with atomic(db):
                batch = self.get_batch(db, batch_id)
                if batch.status == 'cancelled':
                    raise ValueError('Remesa cancelada. Sus archivos históricos no deben presentarse.')
                if all(g.artifact or not any(d.status != 'cancelled' for d in g.debits) for g in batch.groups):
                    return batch
                if batch.status != "prepared" or batch.requested_collection_date < business_today():
                    raise ValueError("La remesa no puede exportarse en su estado o fecha actuales.")
                self.storage.mkdir(parents=True, exist_ok=True)
                for group in batch.groups:
                    live = [d for d in group.debits if d.status != 'cancelled']
                    if not live:
                        continue
                    for debit in live:
                        self._validate_debit(db, debit, bank=True)
                    export_group = SimpleNamespace(id=group.id, snapshot=group.snapshot, batch=batch, debits=live)
                    content = render_bbva(export_group, "RM" + uuid4().hex, now())
                    filename = f"bbva-{uuid4().hex}.xml"
                    path = self.storage / filename
                    with path.open("xb") as file:
                        created_files.append(path)
                        file.write(content)
                    db.add(SepaExportArtifact(group_id=group.id, filename=filename, sha256=sha256(content).hexdigest(),
                        transaction_count=len(live), control_sum=sum(d.amount for d in live)))
                batch.status = "exported"
                batch.exported_at = now()
        except Exception:
            for path in created_files:
                path.unlink(missing_ok=True)
            raise
        return batch

    def artifact_path(self, db, artifact_id):
        artifact = db.get(SepaExportArtifact, artifact_id)
        if not artifact:
            raise ValueError("Archivo no encontrado.")
        path = (self.storage / artifact.filename).resolve()
        if path.parent != self.storage.resolve() or not path.is_file() or sha256(path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError("Archivo ausente o integridad no válida.")
        return path

    def present(self, db, batch_id):
        with atomic(db):
            batch = self.get_batch(db, batch_id)
            if batch.status in {"presented", "partially_collected", "collected"}:
                return batch
            if batch.status != "exported" or not all(g.artifact for g in batch.groups):
                if batch.status != 'exported' or any(not g.artifact and any(d.status != 'cancelled' for d in g.debits) for g in batch.groups):
                    raise ValueError("Exporte todos los grupos antes de confirmar su presentación.")
            # A manual payment after export must not be silently sent to the bank.
            for group in batch.groups:
                for debit in group.debits:
                    if debit.status != 'cancelled':
                        self._validate_debit(db, debit)
            batch.status = "presented"
            batch.presented_at = now()
            for group in batch.groups:
                for debit in group.debits:
                    if debit.status == 'cancelled':
                        continue
                    debit.status = "presented"
                    mandate = self.sepa.get_mandate(db, debit.mandate_id)
                    mandate.last_used_at = batch.requested_collection_date
        return batch

    def collect(self, db, batch_id, debit_ids, effective_date):
        if not debit_ids or len(debit_ids) != len(set(debit_ids)) or effective_date > business_today():
            raise ValueError("Seleccione adeudos sin duplicados y una fecha de cobro real no futura.")
        with atomic(db):
            batch = self.get_batch(db, batch_id)
            if batch.status not in {"presented", "partially_collected", "collected"}:
                raise ValueError("Solo pueden registrarse cobros de remesas presentadas.")
            debits = {d.id: d for g in batch.groups for d in g.debits}
            if not set(debit_ids).issubset(debits):
                raise ValueError("Los adeudos no pertenecen a esta remesa.")
            for i in debit_ids:
                debit = debits[i]
                if debit.status in {'returned', 'cancelled'}:
                    raise ValueError('Un adeudo devuelto o cancelado no se vuelve a cobrar. Requiere un nuevo intento explícito.')
                if debit.payment_id is not None:
                    continue
                self._validate_debit(db, debit)
                payment = Payment(booking_id=debit.booking_id, effective_date=effective_date, amount=debit.amount,
                    currency="EUR", direction="receipt", method="sepa_direct_debit", lifecycle="posted",
                    posted_at=now(), external_reference=debit.end_to_end_id)
                db.add(payment); db.flush()
                for allocation in debit.allocations:
                    db.add(PaymentAllocation(payment_id=payment.id, charge_id=allocation.charge_id, amount=allocation.amount))
                debit.payment_id = payment.id
                debit.status = "collected"
                debit.collected_at = now()
            self._refresh_batch(batch)
        return batch

    @staticmethod
    def _refresh_batch(batch):
        live = [d for g in batch.groups for d in g.debits if d.status != 'cancelled']
        if not live:
            batch.status = 'cancelled'
        elif all(d.payment_id is not None for d in live):
            batch.status = 'collected'
        elif any(d.payment_id is not None for d in live):
            batch.status = 'partially_collected'

    @staticmethod
    def batch_label(batch):
        debits = [d for g in batch.groups for d in g.debits if d.status != 'cancelled']
        returned = sum(d.status == 'returned' for d in debits)
        if returned:
            if returned == len(debits): return 'Devuelta'
            if all(d.payment_id for d in debits): return 'Cobrada con devoluciones'
            return 'Parcialmente cobrada con devoluciones'
        return {'prepared':'Preparada','exported':'Exportada','presented':'Presentada',
                'partially_collected':'Parcialmente cobrada','collected':'Cobrada','cancelled':'Cancelada'}[batch.status]

    def balance_warning(self, db, debit):
        if debit.status not in {'prepared','presented'}:
            return None
        balances = [(a.amount, self.finance.charge_balance(db, a.charge_id)) for a in debit.allocations]
        if any(b is None or b.outstanding_amount < amount for amount,b in balances):
            paid = all(b and b.outstanding_amount == 0 for _,b in balances)
            message = 'Cargo pagado por otro medio.' if paid else 'Saldo reducido por otros pagos; el adeudo supera el saldo pendiente.'
            return message + (' ADVERTENCIA: el adeudo presentado todavía puede ser cobrado por el banco. No se puede registrar un segundo cobro.'
                if debit.status == 'presented' else ' Revise o cancele antes de presentar; el XML no se modifica automáticamente.')
        return None

    def booking_warnings(self, db, booking_id):
        debits = db.scalars(select(SepaDebit).where(SepaDebit.booking_id == booking_id, SepaDebit.status.in_(['prepared','presented']))
            .options(selectinload(SepaDebit.allocations), joinedload(SepaDebit.group)))
        return [(d.group.batch_id, warning) for d in debits if (warning := self.balance_warning(db,d))]

    def cancel(self, db, batch_id, debit_ids):
        if not debit_ids or len(set(debit_ids)) != len(debit_ids):
            raise ValueError('Seleccione adeudos sin duplicados.')
        with atomic(db):
            batch = self.get_batch(db,batch_id)
            debits = {d.id:d for g in batch.groups for d in g.debits}
            if not set(debit_ids).issubset(debits): raise ValueError('Selección ajena a la remesa.')
            if batch.status == 'cancelled': return batch
            if batch.status not in {'prepared','exported'} or batch.presented_at:
                raise ValueError('No se puede cancelar localmente un adeudo ya presentado al banco.')
            selected = [debits[i] for i in debit_ids]
            # Exported bytes are immutable: retire the whole export, never edit it.
            affected = list(debits.values()) if batch.status == 'exported' else selected
            for debit in affected:
                if debit.status == 'cancelled': continue
                if debit.status != 'prepared': raise ValueError('Solo se cancelan adeudos no presentados.')
                paid = all(self.finance.charge_balance(db,a.charge_id).outstanding_amount == 0 for a in debit.allocations)
                debit.status = 'cancelled'; debit.cancelled_at = now()
                debit.cancellation_reason = 'Pagado por otro medio' if paid else 'Cancelación explícita de remesa/adeudo no presentado'
                for allocation in debit.allocations: allocation.reserved = False
            self._refresh_batch(batch)
        return batch

    def return_debits(self, db, batch_id, debit_ids, returned_on, reason=None, reference=None):
        if not debit_ids or len(set(debit_ids)) != len(debit_ids) or returned_on > business_today():
            raise ValueError('Seleccione adeudos y una fecha de devolución real no futura.')
        reason = (reason or '').strip() or None
        reference = (reference or '').strip() or None
        if any(v and len(v)>255 for v in (reason,reference)):
            raise ValueError('Motivo o referencia demasiado largos.')
        with atomic(db):
            batch = self.get_batch(db,batch_id)
            debits = {d.id:d for g in batch.groups for d in g.debits}
            if not set(debit_ids).issubset(debits): raise ValueError('Selección ajena a la remesa.')
            for i in debit_ids:
                debit = debits[i]
                if debit.status == 'returned':
                    if debit.returned_on != returned_on:
                        raise ValueError('Esta devolución ya está registrada con otra fecha.')
                    continue
                original = db.get(Payment,debit.payment_id) if debit.payment_id else None
                if debit.status != 'collected' or not original or original.lifecycle != 'posted' or original.direction != 'receipt' or original.method != 'sepa_direct_debit':
                    raise ValueError('Solo se devuelve un adeudo efectivamente cobrado y no devuelto.')
                if returned_on < original.effective_date:
                    raise ValueError('La devolución no puede ser anterior al cobro original.')
                pairs = list(db.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id == original.id)))
                if {a.charge_id:a.amount for a in pairs} != {a.charge_id:a.amount for a in debit.allocations} or sum(a.amount for a in pairs) != original.amount:
                    raise ValueError('Las asignaciones originales requieren revisión antes de devolver.')
                if db.scalar(select(Payment.id).where(Payment.corrects_payment_id==original.id, Payment.lifecycle=='posted')):
                    raise ValueError('El pago original ya tiene un movimiento compensatorio.')
                if any(self.finance._charge_allocated(db,a.charge_id) < a.amount for a in pairs):
                    raise ValueError('El saldo aplicado ya fue compensado. Revise el historial.')
                reversal = Payment(booking_id=original.booking_id, effective_date=returned_on,
                    amount=original.amount,currency=original.currency,direction='refund',method='sepa_direct_debit',
                    lifecycle='posted',posted_at=now(),corrects_payment_id=original.id,
                    notes=reason,external_reference=reference)
                db.add(reversal); db.flush()
                for allocation in pairs:
                    db.add(PaymentAllocation(payment_id=reversal.id,charge_id=allocation.charge_id,amount=allocation.amount))
                debit.return_payment_id=reversal.id; debit.returned_on=returned_on
                debit.returned_at=now(); debit.return_reason=reason; debit.status='returned'
                for allocation in debit.allocations: allocation.reserved=False
            self._refresh_batch(batch)
        return batch
