import importlib.util
from pathlib import Path

from backend.core.property_address import format_property_address


_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic/versions/e7a9c1d3f428_structured_property_address.py"
)
_SPEC = importlib.util.spec_from_file_location("structured_address_migration", _MIGRATION_PATH)
_MIGRATION = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MIGRATION)
_parse_unambiguous_address = _MIGRATION._parse_unambiguous_address


class Address:
    street = "  Solars "
    street_number = "10"
    floor = " entlo "
    door = None


def test_structured_address_format_and_migration_parser():
    assert format_property_address(Address()) == "Solars 10, entlo"
    assert _parse_unambiguous_address("Solars 10 entlo ") == (
        "Solars", "10", "entlo", None,
    )
    assert _parse_unambiguous_address("Gerona 5 4 4") == (
        "Gerona", "5", "4", "4",
    )


def test_ambiguous_legacy_address_is_not_parsed():
    assert _parse_unambiguous_address("Clemente Gonzálvez Valls 37 4d") is None
