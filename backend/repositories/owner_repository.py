from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.owner import Owner
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.property_ownership import PropertyOwnership
from backend.models.sepa_creditor_profile import SepaCreditorProfile


class OwnerRepository:
    def list(self, db: Session) -> list[Owner]:
        return list(
            db.scalars(
                select(Owner)
                .options(
                    selectinload(Owner.bank_accounts),
                    selectinload(Owner.property_ownerships).selectinload(
                        PropertyOwnership.property
                    ),
                    selectinload(Owner.property_ownerships).selectinload(
                        PropertyOwnership.rent_bank_account
                    ),
                    selectinload(Owner.sepa_creditor_profiles).selectinload(
                        SepaCreditorProfile.bank_account
                    ),
                )
                .order_by(Owner.legal_name, Owner.id)
            )
        )

    def get(self, db: Session, owner_id: int) -> Owner | None:
        return db.scalar(
            select(Owner)
            .options(
                selectinload(Owner.bank_accounts),
                selectinload(Owner.property_ownerships).selectinload(
                    PropertyOwnership.property
                ),
                selectinload(Owner.property_ownerships).selectinload(
                    PropertyOwnership.rent_bank_account
                ),
                selectinload(Owner.sepa_creditor_profiles).selectinload(
                    SepaCreditorProfile.bank_account
                ),
            )
            .where(Owner.id == owner_id)
        )

    def get_account(self, db: Session, account_id: int) -> OwnerBankAccount | None:
        return db.get(OwnerBankAccount, account_id)

    def get_ownership(self, db: Session, ownership_id: int) -> PropertyOwnership | None:
        return db.get(PropertyOwnership, ownership_id)

    def active_ownership(self, db: Session, property_id: int, owner_id: int):
        return db.scalar(
            select(PropertyOwnership).where(
                PropertyOwnership.property_id == property_id,
                PropertyOwnership.owner_id == owner_id,
                PropertyOwnership.active.is_(True),
            )
        )

    def account_in_active_ownership(self, db: Session, account_id: int) -> bool:
        return db.scalar(
            select(PropertyOwnership.id)
            .where(
                PropertyOwnership.rent_bank_account_id == account_id,
                PropertyOwnership.active.is_(True),
            )
            .limit(1)
        ) is not None

    def account_in_active_sepa_profile(self, db: Session, account_id: int) -> bool:
        return db.scalar(
            select(SepaCreditorProfile.id).where(
                SepaCreditorProfile.bank_account_id == account_id,
                SepaCreditorProfile.active.is_(True),
            ).limit(1)
        ) is not None

    def active_property_total(self, db: Session, property_id: int):
        return list(
            db.scalars(
                select(PropertyOwnership).where(
                    PropertyOwnership.property_id == property_id,
                    PropertyOwnership.active.is_(True),
                )
            )
        )
