"""Populate an EMPTY, migrated, non-production database with synthetic examples.

Usage: python -m scripts.seed_owner_economy_demo <absolute sqlite path>
Never reads or copies private source records.
"""
import sys
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal as D
from uuid import uuid4
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from backend.database.session import DATABASE_PATH
from backend.models import Owner, Property, Room, Booking, BookingCharge, Payment, PaymentAllocation, PropertyOwnership
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.owner_settlement import ExpenseCategory, ManagementFeeTerms
from backend.services.owner_settlement_service import OwnerSettlementService
from backend.services.expense_service import ExpenseService


def seed(path):
    path = Path(path).resolve()
    if path == DATABASE_PATH.resolve() or not path.is_file():
        raise RuntimeError("A migrated temporary database is required.")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with Session(engine) as db:
        if db.scalar(select(func.count()).select_from(Booking)) or db.scalar(select(func.count()).select_from(Owner)):
            raise RuntimeError("Refusing to seed a nonempty business database.")
        service, expense_service = OwnerSettlementService(), ExpenseService()
        category = db.scalar(select(ExpenseCategory).where(ExpenseCategory.code == "repair"))
        summary = []
        for number, title, amount, custody, coowners in (
            (1, "Gestor: 1520 menos gastos y honorarios", "1520", "manager", False),
            (2, "Ingreso directo al propietario", "500", "owner", False),
            (3, "Gasto parcialmente pagado", "500", "manager", False),
            (4, "Devolución posterior al cierre", "400", "manager", False),
            (5, "Copropiedad: cobro por gestor", "500", "manager", True),
            (6, "Copropiedad: A recibe todo", "500", "owner", True),
            (7, "Copropiedad: cada uno recibe su mitad", "500", "split", True),
        ):
            p = Property(name=f"Caso {number} · {title}", address="Dirección sintética", city="Elche", owner="")
            owners = [Owner(legal_name=f"Titular sintético {number}-{letter}") for letter in ("AB" if coowners else "A")]
            db.add_all([p, *owners]); db.flush()
            room = Room(property_id=p.id, code=f"DEMO-{number}", active=True)
            db.add(room); db.flush()
            booking = Booking(room_id=room.id, check_in=date(2026, 8, 1), check_out=date(2026, 9, 1))
            db.add(booking); db.flush()
            charge = BookingCharge(booking_id=booking.id, type="rent", concept=f"Renta sintética caso {number}",
                amount=D(amount), due_date=date(2026, 8, 1), service_period_start=date(2026, 8, 1),
                service_period_end=date(2026, 9, 1), lifecycle="posted", posted_at=datetime(2026, 8, 1))
            db.add(charge)
            for owner in owners:
                db.add(PropertyOwnership(property_id=p.id, owner_id=owner.id, ownership_percentage=D("50" if coowners else "100"), active=True))
                db.add(ManagementFeeTerms(property_id=p.id, owner_id=owner.id, effective_from=date(2026, 1, 1),
                    percentage=D("20"), vat_rate=D("0"), withholding_rate=D("0")))
                db.add(OwnerBankAccount(owner_id=owner.id, account_holder_name=owner.legal_name,
                    iban="ES9121000418450200051332", active=True, receives_settlements=True))
            db.commit()
            last_payment = None
            for recipient in (owners if custody == "split" else [owners[0]]):
                value = D(amount) / (2 if custody == "split" else 1)
                payment = Payment(booking_id=booking.id, amount=value, effective_date=date(2026, 8, 15),
                    direction="receipt", method="bank_transfer", lifecycle="posted", posted_at=datetime(2026, 8, 15))
                db.add(payment); db.flush()
                db.add(PaymentAllocation(payment_id=payment.id, charge_id=charge.id, amount=value)); db.commit()
                service.set_custody(db, payment.id, actor="manager" if custody == "manager" else "owner",
                                    owner_id=None if custody == "manager" else recipient.id)
                last_payment = payment
            if number in (1, 3):
                expense = expense_service.create(db, property_id=p.id, category_id=category.id,
                    expense_date=date(2026, 8, 10), concept="Gasto sintético", base_amount="104.54" if number == 1 else "300",
                    vat_rate="0", withholding_rate="0")
                expense_service.pay(db, expense.id, effective_date=date(2026, 8, 20),
                    amount="104.54" if number == 1 else "100", paid_by="manager", request_key=str(uuid4()))
            for owner in owners:
                view = service.preview(db, owner.id, date(2026, 8, 1), date(2026, 9, 1), [p.id])
                if view["errors"]:
                    raise RuntimeError(view["errors"])
                item = service.save_draft(db, owner_id=owner.id, start=date(2026, 8, 1), end=date(2026, 9, 1),
                    property_ids=[p.id], excluded=[], expected=view["fingerprint"], request_key=str(uuid4()))
                summary.append((number, owner.id, item.id, view["totals"]))
                if number == 4:
                    service.close(db, item.id, item.fingerprint)
            if number == 4:
                reversal = Payment(booking_id=booking.id, amount=D(amount), effective_date=date(2026, 9, 1),
                    direction="refund", method="sepa_direct_debit", lifecycle="posted", posted_at=datetime(2026, 9, 1),
                    corrects_payment_id=last_payment.id)
                db.add(reversal); db.flush()
                db.add(PaymentAllocation(payment_id=reversal.id, charge_id=charge.id, amount=D(amount))); db.commit()
                view = service.preview(db, owners[0].id, date(2026, 9, 1), date(2026, 10, 1), [p.id])
                item = service.save_draft(db, owner_id=owners[0].id, start=date(2026, 9, 1), end=date(2026, 10, 1),
                    property_ids=[p.id], excluded=[], expected=view["fingerprint"], request_key=str(uuid4()))
                summary.append(("4 ajuste", owners[0].id, item.id, view["totals"]))
        for row in summary:
            print(row)
    engine.dispose()


if __name__ == "__main__":
    seed(sys.argv[1])
