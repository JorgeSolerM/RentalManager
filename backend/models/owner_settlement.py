"""Owner economics, deliberately separate from tenant receipts and SEPA."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base


class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("total_amount > 0 AND base_amount >= 0 AND vat_amount >= 0 AND withholding_amount >= 0", name="ck_expense_money"),
        CheckConstraint("vat_rate >= 0 AND vat_rate <= 100 AND withholding_rate >= 0 AND withholding_rate <= 100", name="ck_expense_tax"),
        CheckConstraint("borne_by IN ('owner','manager','tenant','other')", name="ck_expense_bearer"),
        CheckConstraint("lifecycle IN ('posted','void')", name="ck_expense_lifecycle"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"))
    category_id: Mapped[int] = mapped_column(ForeignKey("expense_categories.id", ondelete="RESTRICT"))
    expense_date: Mapped[date] = mapped_column(Date)
    concept: Mapped[str] = mapped_column(String(255))
    supplier: Mapped[str | None] = mapped_column(String(180))
    provider_id: Mapped[int | None] = mapped_column(ForeignKey('providers.id', ondelete='RESTRICT'), index=True)
    provider_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    provider: Mapped['Provider | None'] = relationship(lazy='joined')
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    withholding_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    withholding_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    borne_by: Mapped[str] = mapped_column(String(15), default="owner")
    lifecycle: Mapped[str] = mapped_column(String(12), default="posted")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class ExpensePayment(Base):
    __tablename__ = "expense_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_payment_amount"),
        CheckConstraint("direction IN ('payment','reversal')", name="ck_expense_payment_direction"),
        CheckConstraint("paid_by IN ('manager','owner','other')", name="ck_expense_payment_actor"),
        CheckConstraint("(paid_by = 'owner' AND paid_by_owner_id IS NOT NULL) OR (paid_by != 'owner' AND paid_by_owner_id IS NULL)", name="ck_expense_payment_owner"),
        CheckConstraint("(direction = 'reversal' AND corrects_id IS NOT NULL) OR (direction = 'payment' AND corrects_id IS NULL)", name="ck_expense_payment_correction"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id", ondelete="RESTRICT"), index=True)
    effective_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    direction: Mapped[str] = mapped_column(String(12), default="payment")
    paid_by: Mapped[str] = mapped_column(String(12))
    paid_by_owner_id: Mapped[int | None] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"))
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    corrects_id: Mapped[int | None] = mapped_column(ForeignKey("expense_payments.id", ondelete="RESTRICT"))
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    @property
    def lifecycle(self):
        # Registration is an explicit posted cash movement; corrections are
        # new reversal records, never a toggle that erases a previous payment.
        return "posted"


class ManagementFeeTerms(Base):
    __tablename__ = "management_fee_terms"
    __table_args__ = (
        CheckConstraint("percentage >= 0 AND percentage <= 100", name="ck_management_fee_percentage"),
        CheckConstraint("effective_until IS NULL OR effective_until > effective_from", name="ck_management_fee_dates"),
        CheckConstraint("fee_type = 'percentage_on_collected'", name="ck_management_fee_type"),
        CheckConstraint("vat_rate >= 0 AND vat_rate <= 100 AND withholding_rate >= 0 AND withholding_rate <= 100", name="ck_management_fee_tax"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date)
    fee_type: Mapped[str] = mapped_column(String(40), default="percentage_on_collected")
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    fixed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    minimum_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    withholding_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class SettlementChargePolicy(Base):
    __tablename__ = "settlement_charge_policies"
    charge_type: Mapped[str] = mapped_column(String(30), primary_key=True)
    liquidable_to_owner: Mapped[bool] = mapped_column(Boolean)
    included_in_management_fee_base: Mapped[bool] = mapped_column(Boolean)


class PaymentCustody(Base):
    __tablename__ = "payment_custody"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_custody_amount"),
        CheckConstraint("actor IN ('manager','owner')", name="ck_payment_custody_actor"),
        CheckConstraint("(actor = 'owner' AND owner_id IS NOT NULL) OR (actor = 'manager' AND owner_id IS NULL)", name="ck_payment_custody_owner"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), index=True)
    actor: Mapped[str] = mapped_column(String(12))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("owner_bank_accounts.id", ondelete="RESTRICT"))


class OwnerSettlement(Base):
    __tablename__ = "owner_settlements"
    __table_args__ = (
        CheckConstraint("period_end > period_start", name="ck_owner_settlement_period"),
        CheckConstraint("status IN ('draft','closed','cancelled')", name="ck_owner_settlement_status"),
        CheckConstraint("status != 'closed' OR closed_at IS NOT NULL", name="ck_owner_settlement_closed"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    display_name: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(12), default="draft")
    selection: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    # Decimal amounts serialize as strings, never JSON floating-point numbers.
    snapshot: Mapped[dict] = mapped_column(JSON)
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class OwnerSettlementLine(Base):
    __tablename__ = "owner_settlement_lines"
    __table_args__ = (
        UniqueConstraint("owner_id", "source_key", name="uq_owner_settlement_consumption"),
        CheckConstraint("kind IN ('income','expense','prior_balance')", name="ck_owner_settlement_line_kind"),
        CheckConstraint("(kind = 'income' AND payment_allocation_id IS NOT NULL AND expense_payment_id IS NULL AND prior_settlement_id IS NULL) OR (kind = 'expense' AND payment_allocation_id IS NULL AND expense_payment_id IS NOT NULL AND prior_settlement_id IS NULL) OR (kind = 'prior_balance' AND payment_allocation_id IS NULL AND expense_payment_id IS NULL AND prior_settlement_id IS NOT NULL)", name="ck_owner_settlement_line_source"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("owner_settlements.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"))
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    source_key: Mapped[str] = mapped_column(String(100))
    payment_allocation_id: Mapped[int | None] = mapped_column(ForeignKey("payment_allocations.id", ondelete="RESTRICT"))
    expense_payment_id: Mapped[int | None] = mapped_column(ForeignKey("expense_payments.id", ondelete="RESTRICT"))
    prior_settlement_id: Mapped[int | None] = mapped_column(ForeignKey("owner_settlements.id", ondelete="RESTRICT"))
    ownership_id: Mapped[int | None] = mapped_column(ForeignKey("property_ownerships.id", ondelete="RESTRICT"))
    fee_terms_id: Mapped[int | None] = mapped_column(ForeignKey("management_fee_terms.id", ondelete="RESTRICT"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    snapshot: Mapped[dict] = mapped_column(JSON)


class OwnerPayout(Base):
    __tablename__ = "owner_payouts"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_owner_payout_amount"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("owner_settlements.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id", ondelete="RESTRICT"))
    effective_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    bank_account_id: Mapped[int] = mapped_column(ForeignKey("owner_bank_accounts.id", ondelete="RESTRICT"))
    account_snapshot: Mapped[dict] = mapped_column(JSON)
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    @property
    def lifecycle(self):
        return "posted"
