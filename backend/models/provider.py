"""Private supplier directory; never used by the public application."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.base import Base
from backend.core.iban import mask_iban


class Provider(Base):
    __tablename__ = 'providers'
    __table_args__ = (
        CheckConstraint('length(trim(legal_name)) > 0', name='ck_provider_name'),
        CheckConstraint('country IS NULL OR (length(country) = 2 AND country = upper(country))', name='ck_provider_country'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(180))
    tax_id: Mapped[str | None] = mapped_column(String(40))
    address_line: Mapped[str | None] = mapped_column(String(255))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(120))
    province: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(2))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    iban: Mapped[str | None] = mapped_column(String(34))
    default_expense_category_id: Mapped[int | None] = mapped_column(ForeignKey('expense_categories.id', ondelete='RESTRICT'))
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    @property
    def masked_iban(self):
        return mask_iban(self.iban)

    def fiscal_snapshot(self):
        # No bank details or private notes in expense/document snapshots.
        return {field: getattr(self, field) for field in
                ('legal_name', 'tax_id', 'address_line', 'postal_code', 'city', 'province', 'country')}
