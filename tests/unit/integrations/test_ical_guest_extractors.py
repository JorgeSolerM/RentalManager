import pytest

from backend.integrations.ical_guest_extractors import (
    extract_guest_name,
    extract_housinganywhere_guest_name,
)


@pytest.mark.parametrize(
    "summary",
    [
        "Manualmente bloqueado",
        "Bloqueado",
        "Blocked",
        "Reserved",
        "Reservado",
        "Manually blocked",
        "Unavailable",
        "No disponible",
        "Reservas: Blocked",
    ],
)
def test_housinganywhere_generic_blocks_never_produce_guest(summary):
    assert extract_housinganywhere_guest_name(summary) is None


def test_housinganywhere_extracts_name_and_normalizes_only_spaces():
    assert extract_housinganywhere_guest_name(
        "  rEsErVaS:   Aleksandra    Nowakowska  "
    ) == "Aleksandra Nowakowska"
    assert extract_housinganywhere_guest_name(
        "RESERVAS: aLeKsAnDrA"
    ) == "aLeKsAnDrA"


def test_extractor_is_not_applied_to_other_platforms():
    assert extract_guest_name("flatio", "Reservas: Aleksandra") is None
    assert extract_guest_name("spotahome", "Spotahome") is None
    assert extract_guest_name("housinganywhere", "Reservas: Aleksandra") == "Aleksandra"
