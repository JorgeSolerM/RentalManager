"""Synthetic presentation fixtures; no customer or bank data."""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from pypdf import PdfReader
from backend.services.settlement_pdf import render_settlement_pdf


def example_payload():
    rows = [dict(key=str(i), kind='income', property_id=1, room=f'Habitación {i}',
                 concept='Alquiler septiembre', amount=str(amount), fee=str(Decimal(amount)*Decimal('.20')),
                 fee_percentage='20', fee_terms_id=1)
            for i, amount in enumerate(['150','325','300','350','395'],1)]
    rows.append(dict(key='expense',kind='expense',property_id=1,date='2026-09-15',
                     concept='Reparación sintética',amount='104.54'))
    return dict(id=100,identity=dict(issuer='HSI Rents',manager='Gestor sintético',email='gestion@example.test',
        owner='Propietario sintético',properties={'1':'Finca de ejemplo'},
        references={str(i):{'tenant':f'Inquilino {i}'} for i in range(1,6)}),
        start='2026-09-01',end='2026-10-01',closed_at='2026-09-30',rows=rows,
        totals=dict(economic_balance='1111.46',directly_received='0',manager_held_funds='1415.46',
                    inter_owner_difference='0',prior_balance='0',payout_due='1111.46'),
        payouts=[],paid='0',pending='1111.46')


def read(payload):
    return PdfReader(BytesIO(render_settlement_pdf(payload,'2026-09-30')))


def test_five_tenants_one_page_and_financial_parity():
    payload=example_payload(); before=deepcopy(payload)
    reader=read(payload); text=reader.pages[0].extract_text()
    assert len(reader.pages)==1
    assert all(v in text for v in ['1.520,00','104,54','304,00','1.111,46','20 %'])
    assert 'Recibido directamente' not in text and 'OBSERVACIÓN DE CUSTODIA' not in text
    assert 'snapshot' not in text and 'source' not in text
    assert payload==before


def test_conditional_custody():
    payload=example_payload()
    payload['totals'].update(directly_received='500',inter_owner_difference='250',manager_held_funds='0')
    text=read(payload).pages[0].extract_text()
    assert 'Recibido directamente' in text and 'Exceso recibido por copropietario' in text
    assert 'Fondos bajo custodia del gestor' not in text
    payload['totals']['inter_owner_difference']='-250'
    assert 'Pendiente de regularización' in read(payload).pages[0].extract_text()


def test_long_table_repeats_headers():
    payload=example_payload()
    payload['rows']=[{**payload['rows'][0],'concept':f'Línea {i} '+('texto ' * 18)} for i in range(80)]
    reader=read(payload)
    assert len(reader.pages)>2
    assert 'Línea 0' in reader.pages[0].extract_text()
    for page in reader.pages:
        text=page.extract_text()
        assert 'Página' in text
        if 'Línea' in text:
            assert 'Inquilino' in text and 'Concepto' in text and 'Cobrado' in text
