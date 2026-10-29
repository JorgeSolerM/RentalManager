from datetime import date
from urllib.parse import parse_qs, urlsplit
import pytest

from backend.core.verifactu_primitives import alta_hash, test_qr_url


def vector():
    # PUBLIC AEAT example, hash specification v0.1.2, pages 10–11.
    # This identifier is not taken from RentalManager or private files.
    return dict(IDEmisorFactura='89890001K', NumSerieFactura='12345678/G33',
        FechaExpedicionFactura='01-01-2024', TipoFactura='F1', CuotaTotal='12.35',
        ImporteTotal='123.45', Huella='', FechaHoraHusoGenRegistro='2024-01-01T19:20:30+01:00')


def test_official_first_and_chained_hash_vectors():
    first = alta_hash(vector())
    assert first == '3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60'
    second = alta_hash({**vector(), 'Huella': first, 'NumSerieFactura': '12345679/G34',
                       'FechaHoraHusoGenRegistro': '2024-01-01T19:20:35+01:00'})
    assert second == 'F7B94CFD8924EDFF273501B01EE5153E4CE8F259766F88CF6ACB8935802A2B97'


def test_hash_uses_fiscal_fields_not_document_bytes_and_trims():
    assert alta_hash({**vector(), 'IDEmisorFactura': ' 89890001K '}) == alta_hash(vector())
    assert alta_hash({**vector(), 'pdf_hash': 'ignored'}) == alta_hash(vector())
    assert alta_hash({**vector(), 'ImporteTotal': '120.00'}) != alta_hash(vector())


@pytest.mark.parametrize('change', [
    {'Huella': 'invalid'}, {'FechaHoraHusoGenRegistro': '2026-09-01T10:00:00'},
    {'CuotaTotal': '12,35'}, {'ImporteTotal': 'NaN'}, {'TipoFactura': 'R1'},
])
def test_invalid_hash_inputs_rejected(change):
    with pytest.raises(ValueError):
        alta_hash({**vector(), **change})


def test_qr_test_endpoint_encoded_number_and_gross_not_net():
    url = test_qr_url(issuer_nif='89890001K', number='TEST & 2026/1',
                      issue_date=date(2026, 9, 1), gross_invoice_total='367.84')
    parts = urlsplit(url)
    assert parts.scheme == 'https' and parts.netloc == 'prewww2.aeat.es'
    assert parse_qs(parts.query) == dict(nif=['89890001K'], numserie=['TEST & 2026/1'],
                                      fecha=['01-09-2026'], importe=['367.84'])
    assert '%26' in url and '322.24' not in url
