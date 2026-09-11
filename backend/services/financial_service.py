import calendar
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.financial_policy import (
    DEFAULT_CURRENCY,
    DEFAULT_DUE_DAY,
    MONEY_QUANTUM,
    round_money,
)
from backend.core.operation_result import OperationResult
from backend.models.booking import Booking
from backend.models.booking_charge import BookingCharge
from backend.models.booking_financial_terms import BookingFinancialTerms
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.repositories.financial_repository import FinancialRepository
from backend.schemas.financial_schema import (
    BookingLedgerSummary,
    ChargeBalance,
    LegacyPriceCandidate,
    RecurringChargePreview,
)

CENT = MONEY_QUANTUM
ZERO = Decimal("0.00")


class FinancialService:
    def __init__(self):
        self.repository = FinancialRepository()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _money(value, *, allow_zero=True) -> Decimal:
        if isinstance(value, float):
            raise ValueError("financial_amount_float_not_allowed")
        try:
            amount = round_money(Decimal(value))
        except (InvalidOperation, TypeError):
            raise ValueError("financial_amount_invalid")
        if not amount.is_finite() or amount < ZERO or (not allow_zero and amount == ZERO):
            raise ValueError("financial_amount_invalid")
        return amount

    @staticmethod
    def _currency(value: str) -> str:
        value = value.strip().upper()
        if value != DEFAULT_CURRENCY:
            raise ValueError("financial_currency_not_supported")
        return value

    @staticmethod
    def due_date_for_month(year: int, month: int, usual_due_day: int) -> date:
        if not 1 <= usual_due_day <= 31:
            raise ValueError("financial_due_day_invalid")
        return date(year, month, min(usual_due_day, calendar.monthrange(year, month)[1]))

    @staticmethod
    def _next_month(value: date) -> date:
        return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)

    @classmethod
    def preview_monthly_rent(
        cls,
        *,
        check_in: date,
        check_out: date,
        monthly_rent: Decimal,
        usual_due_day: int,
        terms_id: int,
        currency: str = DEFAULT_CURRENCY,
    ) -> list[RecurringChargePreview]:
        """Build calendar-month charges for the half-open stay [check_in, check_out)."""
        if check_out <= check_in:
            raise ValueError("financial_booking_dates_invalid")
        rent = cls._money(monthly_rent)
        if rent == ZERO:
            raise ValueError("financial_amount_invalid")
        cls._currency(currency)
        cls.due_date_for_month(check_in.year, check_in.month, usual_due_day)
        rows: list[RecurringChargePreview] = []
        cursor = date(check_in.year, check_in.month, 1)
        while cursor < check_out:
            month_end = cls._next_month(cursor)
            period_start = max(check_in, cursor)
            period_end = min(check_out, month_end)
            if period_start < period_end:
                days_in_month = (month_end - cursor).days
                occupied_days = (period_end - period_start).days
                amount = rent if occupied_days == days_in_month else round_money(
                    rent * Decimal(occupied_days) / Decimal(days_in_month)
                )
                due_date = cls.due_date_for_month(cursor.year, cursor.month, usual_due_day)
                if not rows and due_date < check_in:
                    due_date = check_in
                rows.append(
                    RecurringChargePreview(
                        type="rent",
                        concept=f"Renta {cursor.strftime('%m/%Y')}",
                        service_period_start=period_start,
                        service_period_end=period_end,
                        due_date=due_date,
                        amount=amount,
                        currency=currency,
                        generation_key=(
                            f"rent:terms-{terms_id}:{period_start.isoformat()}:{period_end.isoformat()}"
                        ),
                    )
                )
            cursor = month_end
        return rows

    @classmethod
    def preview_for_booking(
        cls,
        booking: Booking,
        terms: BookingFinancialTerms,
        *,
        include_deposit: bool = False,
    ) -> list[RecurringChargePreview]:
        if terms.booking_id != booking.id or terms.status != "confirmed":
            raise ValueError("financial_terms_not_confirmed")
        rows = cls.preview_monthly_rent(
            check_in=booking.check_in,
            check_out=booking.check_out,
            monthly_rent=terms.monthly_rent,
            usual_due_day=terms.usual_due_day,
            terms_id=terms.id,
            currency=terms.currency,
        )
        if include_deposit and terms.deposit_agreed > ZERO:
            rows.append(
                RecurringChargePreview(
                    type="security_deposit",
                    concept="Fianza",
                    service_period_start=None,
                    service_period_end=None,
                    due_date=booking.check_in,
                    amount=round_money(terms.deposit_agreed),
                    currency=terms.currency,
                    generation_key=f"security-deposit:terms-{terms.id}",
                )
            )
        return rows

    @staticmethod
    def _fail(db, message):
        db.rollback()
        return OperationResult(success=False, message=message)

    def create_terms_draft(self, db: Session, booking_id: int, effective_from: date, monthly_rent, *, effective_until=None, currency=DEFAULT_CURRENCY, usual_due_day=DEFAULT_DUE_DAY, deposit_agreed=ZERO, notes=None):
        try:
            if db.get(Booking, booking_id) is None:
                return self._fail(db, "booking_not_found")
            if not 1 <= usual_due_day <= 31 or (effective_until and effective_until <= effective_from):
                return self._fail(db, "financial_terms_invalid")
            terms = BookingFinancialTerms(booking_id=booking_id, version=self.repository.next_terms_version(db, booking_id), effective_from=effective_from, effective_until=effective_until, monthly_rent=self._money(monthly_rent, allow_zero=False), currency=self._currency(currency), usual_due_day=usual_due_day, deposit_agreed=self._money(deposit_agreed), notes=notes, status="draft")
            db.add(terms); db.commit(); return OperationResult(success=True, data=terms)
        except ValueError as error:
            return self._fail(db, str(error))
        except IntegrityError:
            return self._fail(db, "financial_terms_invalid")

    def update_terms_draft(self, db: Session, terms_id: int, **changes):
        terms = self.repository.get_terms(db, terms_id)
        if terms is None: return self._fail(db, "financial_terms_not_found")
        if terms.status != "draft": return self._fail(db, "financial_terms_immutable")
        try:
            for key, value in changes.items():
                if key == "monthly_rent": value = self._money(value, allow_zero=False)
                if key == "deposit_agreed": value = self._money(value)
                if key == "currency": value = self._currency(value)
                if key in {"booking_id", "version", "status", "confirmed_at", "supersedes_id"}: return self._fail(db, "financial_terms_field_immutable")
                setattr(terms, key, value)
            if not 1 <= terms.usual_due_day <= 31 or (terms.effective_until and terms.effective_until <= terms.effective_from): return self._fail(db, "financial_terms_invalid")
            db.commit(); return OperationResult(success=True, data=terms)
        except ValueError as error: return self._fail(db, str(error))

    def confirm_terms(self, db: Session, terms_id: int):
        terms = self.repository.get_terms(db, terms_id)
        if terms is None: return self._fail(db, "financial_terms_not_found")
        if terms.status != "draft": return self._fail(db, "financial_terms_not_draft")
        if self.repository.overlapping_confirmed_terms(db, terms): return self._fail(db, "financial_terms_overlap")
        terms.status = "confirmed"; terms.confirmed_at = self._now(); db.commit(); return OperationResult(success=True, data=terms)

    def generate_booking_charges(
        self,
        db: Session,
        booking_id: int,
        terms_id: int,
        *,
        include_deposit: bool = False,
    ):
        booking = db.get(Booking, booking_id)
        terms = self.repository.get_terms(db, terms_id)
        if booking is None:
            return self._fail(db, "booking_not_found")
        if terms is None or terms.booking_id != booking_id or terms.status != "confirmed":
            return self._fail(db, "financial_terms_not_confirmed")
        if len(self.repository.list_terms(db, booking_id)) > 1:
            return self._fail(db, "financial_multiple_terms_not_supported")
        try:
            preview = self.preview_for_booking(
                booking, terms, include_deposit=include_deposit
            )
            existing = self.repository.charge_generation_keys(db, booking_id)
            created = []
            for row in preview:
                if row.generation_key in existing:
                    continue
                charge = BookingCharge(
                    booking_id=booking_id,
                    financial_terms_id=terms.id,
                    type=row.type,
                    direction="debit",
                    concept=row.concept,
                    service_period_start=row.service_period_start,
                    service_period_end=row.service_period_end,
                    due_date=row.due_date,
                    amount=row.amount,
                    currency=row.currency,
                    lifecycle="draft",
                    generation_key=row.generation_key,
                )
                db.add(charge)
                created.append(charge)
            db.commit()
            return OperationResult(success=True, data=created)
        except ValueError as error:
            return self._fail(db, str(error))
        except IntegrityError:
            return self._fail(db, "charge_duplicate_or_invalid")

    def regenerate_draft_charges(
        self,
        db: Session,
        booking_id: int,
        terms_id: int,
        *,
        include_deposit: bool = False,
    ):
        booking = db.get(Booking, booking_id)
        terms = self.repository.get_terms(db, terms_id)
        if booking is None:
            return self._fail(db, "booking_not_found")
        if terms is None or terms.booking_id != booking_id or terms.status != "confirmed":
            return self._fail(db, "financial_terms_not_confirmed")
        if len(self.repository.list_terms(db, booking_id)) > 1:
            return self._fail(db, "financial_multiple_terms_not_supported")
        try:
            preview = self.preview_for_booking(
                booking, terms, include_deposit=include_deposit
            )
            for charge in self.repository.draft_generated_charges(db, booking_id):
                db.delete(charge)
            db.flush()
            existing = self.repository.charge_generation_keys(db, booking_id)
            created = []
            for row in preview:
                if row.generation_key in existing:
                    continue
                charge = BookingCharge(
                    booking_id=booking_id,
                    financial_terms_id=terms.id,
                    type=row.type,
                    direction="debit",
                    concept=row.concept,
                    service_period_start=row.service_period_start,
                    service_period_end=row.service_period_end,
                    due_date=row.due_date,
                    amount=row.amount,
                    currency=row.currency,
                    lifecycle="draft",
                    generation_key=row.generation_key,
                )
                db.add(charge)
                created.append(charge)
            db.commit()
            return OperationResult(success=True, data=created)
        except ValueError as error:
            return self._fail(db, str(error))
        except IntegrityError:
            return self._fail(db, "charge_duplicate_or_invalid")

    def post_generated_drafts(self, db: Session, booking_id: int):
        charges = self.repository.draft_generated_charges(db, booking_id)
        if not charges:
            return self._fail(db, "financial_no_draft_charges")
        now = self._now()
        for charge in charges:
            charge.lifecycle = "posted"
            charge.posted_at = now
        db.commit()
        return OperationResult(success=True, data=charges)

    def generation_state(
        self,
        db: Session,
        booking: Booking,
        terms: BookingFinancialTerms | None,
    ) -> dict[str, bool]:
        if terms is None or terms.status != "confirmed":
            return {"drafts_stale": False, "posted_mismatch": False}
        expected = {
            row.generation_key
            for row in self.preview_for_booking(
                booking, terms, include_deposit=True
            )
        }
        charges = self.repository.list_charges(db, booking.id)
        generated = [charge for charge in charges if charge.generation_key]
        expected_rent = {key for key in expected if key.startswith("rent:")}
        draft_rent = {
            charge.generation_key
            for charge in generated
            if charge.lifecycle == "draft" and charge.type == "rent"
        }
        return {
            "drafts_stale": bool(draft_rent) and draft_rent != expected_rent,
            "posted_mismatch": any(
                charge.lifecycle == "posted" and charge.generation_key not in expected
                for charge in generated
            ),
        }

    def supersede_terms(self, db: Session, terms_id: int, effective_from: date, monthly_rent, **kwargs):
        old = self.repository.get_terms(db, terms_id)
        if old is None or old.status != "confirmed": return self._fail(db, "financial_terms_not_confirmed")
        if effective_from <= old.effective_from or effective_from.day != 1:
            return self._fail(db, "financial_terms_change_requires_full_month")
        try:
            old.status = "superseded"; old.effective_until = effective_from
            new = BookingFinancialTerms(booking_id=old.booking_id, version=self.repository.next_terms_version(db, old.booking_id), effective_from=effective_from, monthly_rent=self._money(monthly_rent), currency=old.currency, usual_due_day=kwargs.get("usual_due_day", old.usual_due_day), deposit_agreed=self._money(kwargs.get("deposit_agreed", old.deposit_agreed)), status="confirmed", confirmed_at=self._now(), supersedes_id=old.id, notes=kwargs.get("notes"))
            db.add(new); db.commit(); return OperationResult(success=True, data=new)
        except Exception: db.rollback(); raise

    def create_charge(self, db: Session, booking_id: int, type: str, concept: str, due_date: date, amount, *, direction=None, currency=DEFAULT_CURRENCY, financial_terms_id=None, service_period_start=None, service_period_end=None, generation_key=None, corrects_charge_id=None, reason=None):
        valid = {"rent","security_deposit","reservation_deposit","utilities","extraordinary","discount","deposit_retention"}
        direction = direction or ("credit" if type == "discount" else "debit")
        if type not in valid or direction != ("credit" if type == "discount" else "debit"): return self._fail(db, "charge_invalid_type_or_direction")
        if db.get(Booking, booking_id) is None: return self._fail(db, "booking_not_found")
        terms = self.repository.get_terms(db, financial_terms_id) if financial_terms_id else None
        if terms and (terms.booking_id != booking_id or terms.currency != currency): return self._fail(db, "charge_terms_mismatch")
        corrected = self.repository.get_charge(db, corrects_charge_id) if corrects_charge_id else None
        if corrects_charge_id and (corrected is None or corrected.booking_id != booking_id): return self._fail(db, "charge_correction_mismatch")
        try:
            charge = BookingCharge(booking_id=booking_id, financial_terms_id=financial_terms_id, type=type, direction=direction, concept=concept.strip(), due_date=due_date, amount=self._money(amount, allow_zero=False), currency=self._currency(currency), service_period_start=service_period_start, service_period_end=service_period_end, generation_key=generation_key, corrects_charge_id=corrects_charge_id, reason=reason)
            db.add(charge); db.commit(); return OperationResult(success=True, data=charge)
        except ValueError as error: return self._fail(db, str(error))
        except IntegrityError: return self._fail(db, "charge_duplicate_or_invalid")

    def update_charge_draft(self, db, charge_id, *, concept=None, due_date=None, amount=None, reason=None):
        charge = self.repository.get_charge(db, charge_id)
        if charge is None: return self._fail(db, "charge_not_found")
        if charge.lifecycle != "draft": return self._fail(db, "charge_immutable")
        try:
            if concept is not None: charge.concept = concept.strip()
            if due_date is not None: charge.due_date = due_date
            if amount is not None: charge.amount = self._money(amount, allow_zero=False)
            if reason is not None: charge.reason = reason
            db.commit(); return OperationResult(success=True, data=charge)
        except ValueError as error: return self._fail(db, str(error))

    def post_charge(self, db, charge_id):
        charge = self.repository.get_charge(db, charge_id)
        if charge is None or charge.lifecycle != "draft": return self._fail(db, "charge_not_draft")
        charge.lifecycle="posted"; charge.posted_at=self._now(); db.commit(); return OperationResult(success=True, data=charge)

    def void_charge(self, db, charge_id, reason):
        charge = self.repository.get_charge(db, charge_id)
        if charge is None or charge.lifecycle != "posted": return self._fail(db, "charge_not_posted")
        if self.repository.allocations_for_charge(db, charge_id): return self._fail(db, "charge_has_allocations")
        charge.lifecycle="void"; charge.voided_at=self._now(); charge.reason=reason; db.commit(); return OperationResult(success=True, data=charge)

    def create_payment(self, db, booking_id, effective_date, amount, direction, method, *, currency=DEFAULT_CURRENCY, external_reference=None, notes=None, corrects_payment_id=None):
        if db.get(Booking, booking_id) is None: return self._fail(db, "booking_not_found")
        if direction not in {"receipt","refund"} or method not in {"bank_transfer","cash","card_or_platform","sepa_direct_debit","other"}: return self._fail(db, "payment_invalid")
        corrected = self.repository.get_payment(db, corrects_payment_id) if corrects_payment_id else None
        if corrects_payment_id and (corrected is None or corrected.booking_id != booking_id): return self._fail(db, "payment_correction_mismatch")
        try:
            payment=Payment(booking_id=booking_id,effective_date=effective_date,amount=self._money(amount,allow_zero=False),currency=self._currency(currency),direction=direction,method=method,external_reference=external_reference,notes=notes,corrects_payment_id=corrects_payment_id)
            db.add(payment); db.commit(); return OperationResult(success=True,data=payment)
        except ValueError as error: return self._fail(db, str(error))
        except IntegrityError: return self._fail(db,"payment_invalid")

    def update_payment_draft(self, db, payment_id, *, effective_date=None, amount=None, method=None, external_reference=None, notes=None):
        payment = self.repository.get_payment(db, payment_id)
        if payment is None: return self._fail(db, "payment_not_found")
        if payment.lifecycle != "draft": return self._fail(db, "payment_immutable")
        try:
            if effective_date is not None: payment.effective_date = effective_date
            if amount is not None: payment.amount = self._money(amount, allow_zero=False)
            if method is not None:
                if method not in {"bank_transfer","cash","card_or_platform","sepa_direct_debit","other"}: return self._fail(db, "payment_invalid")
                payment.method = method
            if external_reference is not None: payment.external_reference = external_reference
            if notes is not None: payment.notes = notes
            db.commit(); return OperationResult(success=True, data=payment)
        except ValueError as error: return self._fail(db, str(error))

    def post_payment(self, db, payment_id):
        payment=self.repository.get_payment(db,payment_id)
        if payment is None or payment.lifecycle!="draft": return self._fail(db,"payment_not_draft")
        payment.lifecycle="posted"; payment.posted_at=self._now(); db.commit(); return OperationResult(success=True,data=payment)

    def void_payment(self, db, payment_id, notes=None):
        payment=self.repository.get_payment(db,payment_id)
        if payment is None or payment.lifecycle!="posted": return self._fail(db,"payment_not_posted")
        from sqlalchemy import or_, select
        from backend.models.sepa_collection import SepaDebit
        from backend.models.owner_settlement import OwnerSettlementLine
        if db.scalar(select(OwnerSettlementLine.id).join(PaymentAllocation,
                OwnerSettlementLine.payment_allocation_id == PaymentAllocation.id)
                .where(PaymentAllocation.payment_id == payment_id).limit(1)):
            return self._fail(db, 'payment_settled_requires_correction')
        if db.scalar(select(SepaDebit.id).where(or_(SepaDebit.payment_id==payment_id, SepaDebit.return_payment_id==payment_id)).limit(1)):
            return self._fail(db,'payment_sepa_requires_audited_operation')
        payment.lifecycle="void"; payment.voided_at=self._now(); payment.notes=notes or payment.notes; db.commit(); return OperationResult(success=True,data=payment)

    def _charge_allocated(self, db, charge_id):
        total=ZERO
        for allocation,payment in self.repository.allocations_for_charge(db,charge_id):
            if payment.lifecycle=="posted": total += allocation.amount if payment.direction=="receipt" else -allocation.amount
        return total.quantize(CENT)

    def allocate(self, db, payment_id, charge_id, amount):
        payment=self.repository.get_payment(db,payment_id); charge=self.repository.get_charge(db,charge_id)
        if not payment or not charge or payment.lifecycle!="posted" or charge.lifecycle!="posted": return self._fail(db,"allocation_requires_posted_records")
        if payment.booking_id!=charge.booking_id or payment.currency!=charge.currency or charge.direction!="debit": return self._fail(db,"allocation_mismatch")
        try: value=self._money(amount,allow_zero=False)
        except ValueError as error: return self._fail(db,str(error))
        if Decimal(self.repository.allocation_total_for_payment(db,payment_id)) + value > payment.amount: return self._fail(db,"payment_overallocated")
        allocated=self._charge_allocated(db,charge_id)
        if payment.direction=="receipt" and value > charge.amount-allocated: return self._fail(db,"charge_overallocated")
        if payment.direction=="refund" and value > allocated: return self._fail(db,"refund_exceeds_allocated")
        try:
            allocation=PaymentAllocation(payment_id=payment_id,charge_id=charge_id,amount=value); db.add(allocation); db.commit(); return OperationResult(success=True,data=allocation)
        except IntegrityError: return self._fail(db,"allocation_duplicate")

    def charge_balance(self, db, charge_id, today=None):
        charge=self.repository.get_charge(db,charge_id)
        if charge is None: return None
        allocated=self._charge_allocated(db,charge_id); original=charge.amount if charge.direction=="debit" else -charge.amount
        outstanding=ZERO if charge.lifecycle=="void" else original-allocated
        status="void" if charge.lifecycle=="void" else ("credit" if charge.direction=="credit" else ("paid" if outstanding==ZERO else "partial" if allocated>ZERO else "unpaid"))
        return ChargeBalance(original.quantize(CENT),allocated,outstanding.quantize(CENT),status,bool(charge.lifecycle=="posted" and charge.direction=="debit" and outstanding>ZERO and charge.due_date < (today or business_today())))

    def booking_summary(self, db, booking_id, today=None):
        charges=self.repository.list_charges(db,booking_id); payments=self.repository.list_payments(db,booking_id)
        balances=[self.charge_balance(db,c.id,today) for c in charges if c.lifecycle=="posted"]
        charged=sum((b.original_amount for b in balances),ZERO); allocated=sum((b.allocated_amount for b in balances),ZERO)
        received=sum(((p.amount if p.direction=="receipt" else -p.amount) for p in payments if p.lifecycle=="posted"),ZERO)
        overdue=sum((b.outstanding_amount for b in balances if b.overdue),ZERO)
        return BookingLedgerSummary(charged.quantize(CENT),received.quantize(CENT),allocated.quantize(CENT),(received-allocated).quantize(CENT),(charged-allocated).quantize(CENT),overdue.quantize(CENT))

    def legacy_price_candidate(self, db, booking_id):
        booking=db.get(Booking,booking_id)
        if booking is None: return None
        return LegacyPriceCandidate(Decimal(str(booking.price)).quantize(CENT) if booking.price is not None else None)
