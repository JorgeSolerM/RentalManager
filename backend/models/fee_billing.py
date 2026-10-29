"""Private fee billing foundations. No credentials or tenant payments live here."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class FeeTaxConfiguration(Base):
    __tablename__ = 'fee_tax_configurations'
    id: Mapped[int] = mapped_column(primary_key=True)
    terms_id: Mapped[int] = mapped_column(ForeignKey('management_fee_terms.id', ondelete='RESTRICT'), unique=True)
    configuration: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class InvoiceIssuerProfile(Base):
    __tablename__ = 'invoice_issuer_profiles'
    id: Mapped[int] = mapped_column(primary_key=True)
    # Explicit fiscal identity; not seeded from contact, Owner or SEPA settings.
    identity: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class OwnerFiscalIdentity(Base):
    __tablename__ = 'owner_fiscal_identities'
    owner_id: Mapped[int] = mapped_column(ForeignKey('owners.id', ondelete='RESTRICT'), primary_key=True)
    identification_type: Mapped[str] = mapped_column(String(12))
    identification_country: Mapped[str | None] = mapped_column(String(2))
    business_recipient: Mapped[bool | None] = mapped_column(Boolean)


class InvoiceSeries(Base):
    __tablename__ = 'invoice_series'
    __table_args__ = (
        UniqueConstraint('issuer_id', 'prefix', name='uq_invoice_series_prefix'),
        CheckConstraint('counter >= 0 AND padding >= 1 AND padding <= 12', name='ck_invoice_series_counter'),
        CheckConstraint("document_type IN ('ordinary','rectifying')", name='ck_invoice_series_type'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    issuer_id: Mapped[int] = mapped_column(ForeignKey('invoice_issuer_profiles.id', ondelete='RESTRICT'))
    prefix: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120), default='Serie de pruebas')
    document_type: Mapped[str] = mapped_column(String(12), default='ordinary')
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    counter: Mapped[int] = mapped_column(Integer, default=0)
    padding: Mapped[int] = mapped_column(Integer, default=6)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FeeObligation(Base):
    __tablename__ = 'fee_obligations'
    __table_args__ = (
        UniqueConstraint('owner_id', 'source_key', name='uq_fee_obligation_source'),
        CheckConstraint('amount > 0', name='ck_fee_obligation_amount'),
        CheckConstraint("kind IN ('expense_advance','management_fee','other_adjustment')", name='ck_fee_obligation_kind'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('owners.id', ondelete='RESTRICT'), index=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('owner_settlements.id', ondelete='RESTRICT'))
    source_line_id: Mapped[int] = mapped_column(ForeignKey('owner_settlement_lines.id', ondelete='RESTRICT'))
    source_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(24))
    effective_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    snapshot: Mapped[dict] = mapped_column(JSON)


class FeeObligationAdjustment(Base):
    __tablename__ = 'fee_obligation_adjustments'
    __table_args__ = (CheckConstraint('amount != 0', name='ck_fee_adjustment_amount'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    obligation_id: Mapped[int] = mapped_column(ForeignKey('fee_obligations.id', ondelete='RESTRICT'), index=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('owner_settlements.id', ondelete='RESTRICT'))
    source_key: Mapped[str] = mapped_column(String(120), unique=True)
    effective_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reason: Mapped[str] = mapped_column(String(255))


class FeeFund(Base):
    __tablename__ = 'fee_funds'
    __table_args__ = (CheckConstraint('amount > 0', name='ck_fee_fund_amount'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('owners.id', ondelete='RESTRICT'), index=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('owner_settlements.id', ondelete='RESTRICT'))
    source_line_id: Mapped[int] = mapped_column(ForeignKey('owner_settlement_lines.id', ondelete='RESTRICT'), unique=True)
    effective_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class FeeCompensation(Base):
    __tablename__ = 'fee_compensations'
    __table_args__ = (
        CheckConstraint('amount > 0', name='ck_fee_compensation_amount'),
        CheckConstraint("direction IN ('application','reversal')", name='ck_fee_compensation_direction'),
        CheckConstraint("(direction = 'application' AND corrects_id IS NULL) OR (direction = 'reversal' AND corrects_id IS NOT NULL)", name='ck_fee_compensation_correction'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    obligation_id: Mapped[int] = mapped_column(ForeignKey('fee_obligations.id', ondelete='RESTRICT'), index=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey('fee_funds.id', ondelete='RESTRICT'), index=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('owner_settlements.id', ondelete='RESTRICT'))
    effective_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    direction: Mapped[str] = mapped_column(String(12), default='application')
    corrects_id: Mapped[int | None] = mapped_column(ForeignKey('fee_compensations.id', ondelete='RESTRICT'))
    request_key: Mapped[str] = mapped_column(String(100), unique=True)
    reason: Mapped[str | None] = mapped_column(String(255))


class FeeCompensationRun(Base):
    """Persist even no-op requests so a retry never acquires new obligations."""
    __tablename__ = 'fee_compensation_runs'
    request_key: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


class ManagementFeeInvoice(Base):
    __tablename__ = 'management_fee_invoices'
    __table_args__ = (
        CheckConstraint("status IN ('draft','issued')", name='ck_fee_invoice_status'),
        CheckConstraint("(status='draft' AND number IS NULL AND issued_at IS NULL) OR (status='issued' AND number IS NOT NULL AND issued_at IS NOT NULL)", name='ck_fee_invoice_issued'),
        UniqueConstraint('issuer_id', 'number', name='uq_fee_invoice_number'),
        Index('uq_invoice_taxpayer_number', text("json_extract(snapshot, '$.issuer.tax_id')"),
              'number', unique=True, sqlite_where=text("status = 'issued'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('owner_settlements.id', ondelete='RESTRICT'), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('owners.id', ondelete='RESTRICT'))
    issuer_id: Mapped[int] = mapped_column(ForeignKey('invoice_issuer_profiles.id', ondelete='RESTRICT'))
    series_id: Mapped[int] = mapped_column(ForeignKey('invoice_series.id', ondelete='RESTRICT'))
    status: Mapped[str] = mapped_column(String(12), default='draft')
    number: Mapped[str | None] = mapped_column(String(60))
    issue_date: Mapped[date] = mapped_column(Date)
    snapshot: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime)
    document_type: Mapped[str] = mapped_column(String(12), default='ordinary')
    corrects_invoice_id: Mapped[int | None] = mapped_column(ForeignKey('management_fee_invoices.id', ondelete='RESTRICT'))
    correction_reason: Mapped[str | None] = mapped_column(String(500))


class InvoiceRectificationNotice(Base):
    __tablename__ = 'invoice_rectification_notices'
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey('management_fee_invoices.id', ondelete='RESTRICT'))
    source_line_id: Mapped[int] = mapped_column(ForeignKey('owner_settlement_lines.id', ondelete='RESTRICT'), unique=True)
    reason: Mapped[str] = mapped_column(String(255))


class ManagementFeeInvoiceLine(Base):
    __tablename__ = 'management_fee_invoice_lines'
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey('management_fee_invoices.id', ondelete='RESTRICT'), index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey('properties.id', ondelete='RESTRICT'))
    snapshot: Mapped[dict] = mapped_column(JSON)


class ManagementFeeInvoiceSource(Base):
    __tablename__ = 'management_fee_invoice_sources'
    line_id: Mapped[int] = mapped_column(ForeignKey('management_fee_invoice_lines.id', ondelete='RESTRICT'), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey('owner_settlement_lines.id', ondelete='RESTRICT'), primary_key=True, unique=True)


class FiscalChainState(Base):
    __tablename__ = 'fiscal_chain_states'
    # One chain per taxpayer/SIF installation/environment, NEVER per Owner/series.
    chain_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    last_record_id: Mapped[int | None] = mapped_column(Integer)
    last_hash: Mapped[str | None] = mapped_column(String(64))


class InvoiceFiscalRecord(Base):
    __tablename__ = 'invoice_fiscal_records'
    __table_args__ = (
        CheckConstraint("kind IN ('alta','subsanacion','anulacion')", name='ck_fiscal_record_kind'),
        Index('uq_invoice_initial_alta', 'invoice_id', unique=True,
              sqlite_where=text("kind = 'alta'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey('management_fee_invoices.id', ondelete='RESTRICT'))
    chain_key: Mapped[str] = mapped_column(ForeignKey('fiscal_chain_states.chain_key', ondelete='RESTRICT'))
    kind: Mapped[str] = mapped_column(String(16), default='alta')
    payload: Mapped[dict] = mapped_column(JSON)
    generated_at: Mapped[str] = mapped_column(String(40))
    hash: Mapped[str] = mapped_column(String(64))
    previous_record_id: Mapped[int | None] = mapped_column(ForeignKey('invoice_fiscal_records.id', ondelete='RESTRICT'))


class FiscalSubmission(Base):
    __tablename__ = 'fiscal_submissions'
    __table_args__ = (CheckConstraint("status IN ('pending','sending','accepted','accepted_with_errors','rejected','unknown','retry_pending')", name='ck_fiscal_submission_status'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey('invoice_fiscal_records.id', ondelete='RESTRICT'), unique=True)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    environment: Mapped[str] = mapped_column(String(12))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class FiscalSubmissionAttempt(Base):
    __tablename__ = 'fiscal_submission_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey('fiscal_submissions.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    result: Mapped[str] = mapped_column(String(30))
    response: Mapped[dict] = mapped_column(JSON)


from backend.database.fee_billing_guards import register
register(Base.metadata)
