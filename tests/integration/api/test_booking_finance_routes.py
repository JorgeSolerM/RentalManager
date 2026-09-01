from datetime import date
from decimal import Decimal

from sqlalchemy import select
from fastapi.testclient import TestClient

from backend.models.booking import Booking
from backend.models.booking_charge import BookingCharge
from backend.models.booking_party import BookingParty
from backend.models.person import Person
from backend.models.property import Property
from backend.models.room import Room
from backend.public.app_factory import create_public_app
from backend.public.database import get_public_db


def make_finance_booking(db, *, origin="manual"):
    prop = Property(name="Finanzas", address="Calle", city="Elche", owner="HSI", active=True)
    db.add(prop); db.flush()
    room = Room(property_id=prop.id, code="F01", display_order=1, active=True, base_price=Decimal("999"))
    db.add(room); db.flush()
    booking = Booking(
        room_id=room.id, origin=origin, check_in=date(2026, 9, 16),
        check_out=date(2026, 11, 1), price=Decimal("375"), source_guest_name="Nombre recibido",
    )
    db.add(booking); db.commit()
    return booking


def test_finance_page_uses_explicit_legacy_suggestion_and_never_room_price(client, db_session):
    booking = make_finance_booking(db_session)

    page = client.get(f"/bookings/{booking.id}/finance")
    suggested = client.get(f"/bookings/{booking.id}/finance?use_legacy_price=true")

    assert page.status_code == 200
    assert "Economía sin configurar" in page.text
    assert "Precio registrado anteriormente" in page.text
    assert 'value="375.00"' not in page.text
    assert 'value="375.00"' in suggested.text
    assert "999" not in page.text
    assert "No hay arrendatario ni responsable de pago clasificados para esta reserva." in page.text


def test_finance_flow_renders_roles_previews_generates_and_posts(client, db_session):
    booking = make_finance_booking(db_session, origin="housinganywhere")
    tenant = Person(full_name="Arrendataria Uno", active=True)
    payer = Person(full_name="Pagador Dos", active=True)
    db_session.add_all([tenant, payer]); db_session.flush()
    db_session.add_all([
        BookingParty(booking_id=booking.id, person_id=tenant.id, role="tenant"),
        BookingParty(booking_id=booking.id, person_id=payer.id, role="payer"),
    ])
    db_session.commit()

    saved = client.post(
        f"/bookings/{booking.id}/finance/terms",
        data={"monthly_rent": "400.00", "deposit_agreed": "350.00", "usual_due_day": "31"},
        follow_redirects=False,
    )
    terms = booking.financial_terms[0]
    confirmed = client.post(
        f"/bookings/{booking.id}/finance/terms/{terms.id}/confirm",
        follow_redirects=False,
    )
    preview = client.get(f"/bookings/{booking.id}/finance")
    assert db_session.scalar(select(BookingCharge).where(BookingCharge.booking_id == booking.id)) is None
    generated = client.post(
        f"/bookings/{booking.id}/finance/generate",
        data={"terms_id": terms.id, "include_deposit": "true"},
        follow_redirects=False,
    )
    posted = client.post(
        f"/bookings/{booking.id}/finance/post", follow_redirects=False
    )

    assert saved.status_code == confirmed.status_code == generated.status_code == posted.status_code == 303
    assert "Previsualización de mensualidades" in preview.text
    assert "200.00" in preview.text
    assert "16/09/2026 – 30/09/2026" in preview.text
    assert "01/10/2026 – 31/10/2026" in preview.text
    assert "Arrendataria Uno" in preview.text and "Pagador Dos" in preview.text
    assert "Economía gestionada localmente" in preview.text
    charges = db_session.scalars(select(BookingCharge).where(BookingCharge.booking_id == booking.id)).all()
    assert len(charges) == 3
    assert all(charge.lifecycle == "posted" for charge in charges)
    assert booking.price == Decimal("375.00")


def test_finance_page_warns_when_tenant_exists_without_payer(client, db_session):
    booking = make_finance_booking(db_session)
    tenant = Person(full_name="Arrendataria", active=True)
    db_session.add(tenant); db_session.flush()
    db_session.add(BookingParty(booking_id=booking.id, person_id=tenant.id, role="tenant"))
    db_session.commit()

    page = client.get(f"/bookings/{booking.id}/finance")

    assert page.status_code == 200
    assert "No hay responsable de pago clasificado para esta reserva." in page.text
    assert "No hay arrendatario ni responsable" not in page.text


def test_finance_routes_are_admin_only_and_public_pages_do_not_expose_ledger(
    client, db_session
):
    booking = make_finance_booking(db_session)
    client.post(
        f"/bookings/{booking.id}/finance/terms",
        data={"monthly_rent": "432.17", "deposit_agreed": "321.09", "usual_due_day": "1"},
    )

    public_app = create_public_app()
    def override_public_db():
        yield db_session

    public_app.dependency_overrides[get_public_db] = override_public_db
    with TestClient(public_app) as public_client:
        assert public_client.get(f"/bookings/{booking.id}/finance").status_code == 404
        public_home = public_client.get("/")
        assert "432.17" not in public_home.text
        assert "321.09" not in public_home.text
