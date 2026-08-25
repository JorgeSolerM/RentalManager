from datetime import date

from pydantic import BaseModel, ConfigDict


class BookingResponse(BaseModel):

    id: int

    room_id: int

    guest_name: str | None

    origin: str

    check_in: date

    check_out: date

    expected_arrival_date: date | None = None

    expected_departure_date: date | None = None

    price: float | None

    notes: str | None

    editable: bool

    external_block_deletable: bool = False

    model_config = ConfigDict(
        from_attributes=True,
    )


class BookingCreate(BaseModel):
    pass


class BookingUpdate(BaseModel):
    pass
