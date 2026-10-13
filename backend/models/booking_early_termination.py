"""Administrative departure history, separate from cancellation and the ledger."""
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, JSON, CheckConstraint, func, event, DDL
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database.base import Base


class BookingEarlyTermination(Base):
    __tablename__ = 'booking_early_terminations'
    __table_args__ = (
        CheckConstraint('effective_departure > original_check_in AND effective_departure < original_check_out', name='ck_early_departure_interval'),
        CheckConstraint('economic_last_day >= original_check_in AND economic_last_day < original_check_out', name='ck_early_economic_interval'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey('bookings.id', ondelete='RESTRICT'), unique=True)
    request_key: Mapped[str] = mapped_column(String(36), unique=True)
    original_check_in: Mapped[date] = mapped_column(Date)
    original_check_out: Mapped[date] = mapped_column(Date)
    effective_departure: Mapped[date] = mapped_column(Date)
    economic_last_day: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    snapshot: Mapped[dict] = mapped_column(JSON)
    booking: Mapped['Booking'] = relationship(back_populates='early_termination')
    source_state: Mapped['BookingEarlyTerminationSourceState | None'] = relationship(uselist=False)


class BookingEarlyTerminationSourceState(Base):
    __tablename__ = 'booking_early_termination_source_states'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    termination_id: Mapped[int] = mapped_column(ForeignKey('booking_early_terminations.id', ondelete='RESTRICT'), unique=True)
    source_check_in: Mapped[date] = mapped_column(Date)
    source_check_out: Mapped[date] = mapped_column(Date)
    seen_at: Mapped[datetime] = mapped_column(DateTime)


for action in ('UPDATE', 'DELETE'):
    event.listen(BookingEarlyTermination.__table__, 'after_create', DDL(
        f"CREATE TRIGGER early_termination_immutable_{action.lower()} BEFORE {action} ON booking_early_terminations BEGIN SELECT RAISE(ABORT, 'Early termination history is immutable'); END").execute_if(dialect='sqlite'))
event.listen(BookingEarlyTermination.__table__, 'after_create', DDL(
    "CREATE TRIGGER early_termination_dates_guard BEFORE UPDATE OF check_in, check_out, expected_departure_date ON bookings WHEN EXISTS (SELECT 1 FROM booking_early_terminations t WHERE t.booking_id=OLD.id AND (NEW.check_in!=t.original_check_in OR NEW.check_out!=t.effective_departure OR (NEW.expected_departure_date IS NOT NULL AND NEW.expected_departure_date!=t.effective_departure))) BEGIN SELECT RAISE(ABORT, 'Early termination dates are protected'); END").execute_if(dialect='sqlite'))
