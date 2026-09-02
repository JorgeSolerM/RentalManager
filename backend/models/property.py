from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.base import Base
from backend.models.feature import property_features
from backend.models.rental_requirement import property_requirements


class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (
        CheckConstraint(
            "minimum_tenant_age IS NULL OR minimum_tenant_age >= 0",
            name="ck_properties_minimum_tenant_age_nonnegative",
        ),
        CheckConstraint(
            "maximum_tenant_age IS NULL OR maximum_tenant_age >= 0",
            name="ck_properties_maximum_tenant_age_nonnegative",
        ),
        CheckConstraint(
            "minimum_tenant_age IS NULL OR maximum_tenant_age IS NULL "
            "OR minimum_tenant_age <= maximum_tenant_age",
            name="ck_properties_tenant_age_range",
        ),
        CheckConstraint(
            "shared_full_bathroom_count IS NULL OR shared_full_bathroom_count >= 0",
            name="ck_properties_shared_full_bathroom_count_nonnegative",
        ),
        CheckConstraint(
            "shared_toilet_count IS NULL OR shared_toilet_count >= 0",
            name="ck_properties_shared_toilet_count_nonnegative",
        ),
        Index(
            "uq_properties_public_slug",
            "public_slug",
            unique=True,
            sqlite_where=text("public_slug IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    alias: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Structured address fields are the source of truth for new writes.
    # ``address`` remains temporarily as a legacy compatibility value while
    # historical ambiguous rows are reviewed.
    street: Mapped[str | None] = mapped_column(String(180), nullable=True)
    street_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(30), nullable=True)
    door: Mapped[str | None] = mapped_column(String(30), nullable=True)

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    owner: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    public_title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    public_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    public_slug: Mapped[str | None] = mapped_column(String(180), nullable=True)
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    smoking_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pets_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    musical_instruments_allowed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    minimum_tenant_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_tenant_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shared_full_bathroom_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    shared_toilet_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("managers.id", ondelete="SET NULL"), nullable=True, index=True
    )

    manager: Mapped["Manager | None"] = relationship(back_populates="properties")

    rooms: Mapped[list["Room"]] = relationship(
        back_populates="property",
        order_by="Room.display_order",
        passive_deletes="all",
    )

    features: Mapped[list["Feature"]] = relationship(
        secondary=property_features,
        back_populates="properties",
        order_by="Feature.display_order, Feature.name",
    )

    requirements: Mapped[list["RentalRequirement"]] = relationship(
        secondary=property_requirements,
        back_populates="properties",
        order_by="RentalRequirement.display_order, RentalRequirement.public_name",
    )

    photos: Mapped[list["PropertyPhoto"]] = relationship(
        back_populates="property",
        order_by="PropertyPhoto.position, PropertyPhoto.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    ownerships: Mapped[list["PropertyOwnership"]] = relationship(
        back_populates="property",
        order_by="PropertyOwnership.id",
        passive_deletes="all",
    )
