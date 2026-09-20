from pydantic import BaseModel

class BookingPersonLink(BaseModel):
    id: int
    name: str
