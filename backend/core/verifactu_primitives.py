"""AEAT hash v0.1.2 and QR URL v0.5.0. Pure functions, no HTTP calls.

The input monetary strings must be the same frozen values used by the XML.
These primitives alone are not a compliant SIF or an AEAT submission client.
"""
from datetime import date, datetime
from hashlib import sha256
import re
from urllib.parse import urlencode

from backend.services.settlement_money import money

ALTA_FIELDS = ('IDEmisorFactura', 'NumSerieFactura', 'FechaExpedicionFactura',
               'TipoFactura', 'CuotaTotal', 'ImporteTotal', 'Huella', 'FechaHoraHusoGenRegistro')
TEST_QR_URL = 'https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR'


def alta_hash(values):
    if not all(key in values for key in ALTA_FIELDS):
        raise ValueError('Registro fiscal incompleto.')
    fields = {key: str(values[key]).strip() for key in ALTA_FIELDS}
    if any(not value for key, value in fields.items() if key != 'Huella'):
        raise ValueError('Registro fiscal incompleto.')
    if fields['TipoFactura'] != 'F1':
        raise ValueError('Solo se prepara el alta de factura ordinaria completa.')
    if fields['Huella'] and not re.fullmatch(r'[0-9A-F]{64}', fields['Huella']):
        raise ValueError('Huella anterior no válida.')
    if not re.fullmatch(r'[A-Z0-9]{9}', fields['IDEmisorFactura']):
        raise ValueError('Formato de NIF emisor no válido.')
    if len(fields['NumSerieFactura']) > 60 or any(not 32 <= ord(c) <= 126 for c in fields['NumSerieFactura']):
        raise ValueError('Número fiscal no válido.')
    try:
        if not re.fullmatch(r'\d{2}-\d{2}-\d{4}', fields['FechaExpedicionFactura']):
            raise ValueError
        datetime.strptime(fields['FechaExpedicionFactura'], '%d-%m-%Y')
        stamp = datetime.fromisoformat(fields['FechaHoraHusoGenRegistro'])
        if stamp.utcoffset() is None:
            raise ValueError
        for key in ('CuotaTotal', 'ImporteTotal'):
            if not re.fullmatch(r'-?\d+(\.\d{1,2})?', fields[key]):
                raise ValueError
            money(fields[key], signed=True)
    except (TypeError, ValueError):
        raise ValueError('Fechas o importes fiscales no válidos.') from None
    canonical = '&'.join(f'{key}={fields[key]}' for key in ALTA_FIELDS)
    return sha256(canonical.encode('utf-8')).hexdigest().upper()


def test_qr_url(*, issuer_nif, number, issue_date, gross_invoice_total):
    """Only the official external-test endpoint; never infer a net total."""
    if not re.fullmatch(r'[A-Z0-9]{9}', issuer_nif or ''):
        raise ValueError('Formato de NIF emisor no válido.')
    if not number or len(number) > 60 or any(not 32 <= ord(char) <= 126 for char in number):
        raise ValueError('Número de factura no válido para el QR.')
    if type(issue_date) is not date:
        raise ValueError('Fecha de expedición no válida.')
    return TEST_QR_URL + '?' + urlencode(dict(nif=issuer_nif, numserie=number,
        fecha=issue_date.strftime('%d-%m-%Y'), importe=str(money(gross_invoice_total, signed=True))))


test_qr_url.__test__ = False
