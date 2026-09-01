from datetime import date

from pydantic import BaseModel, ConfigDict


class PersonData(BaseModel):
    id: int
    full_name: str
    display_name: str | None = None
    phone: str | None = None
    email: str | None = None
    iban: str | None = None
    document_type: str | None = None
    document_number: str | None = None
    document_issuer_country: str | None = None
    birth_date: date | None = None
    nationality: str | None = None
    address_line: str | None = None
    postal_code: str | None = None
    city: str | None = None
    province: str | None = None
    country: str | None = None
    notes: str | None = None
    active: bool
    verification_status: str
    source: str

    model_config = ConfigDict(from_attributes=True)
