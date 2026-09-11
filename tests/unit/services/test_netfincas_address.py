import pytest
from backend.services.netfincas_address import address_line
from backend.services.netfincas_reconciliation import source_values


@pytest.mark.parametrize('value,expected',[
    ('ESPAÑA','ES'),(' españa ','ES'),('es','ES'),('Italia','IT'),('IT','IT'),
    (None,None),('',None),('unknown',None),('999',None),('ZZ',None),
])
def test_country_never_candidate(value,expected):
    assert 'country' not in source_values({'PAIS':value})


def test_foreign_structured_address():
    row=dict(DIRSIGLA='VIA',DIR='STRADA SINTETICA',DIRNUM='12',DIRPISO='2',DIRLETRA='B',
        CP='00100',POB='LOCALITA TEST',PROVINCIA='PROVINCIA TEST',PAIS='ITALIA')
    values=source_values(row)
    assert values['address_line']=='VIA STRADA SINTETICA 12, planta 2, puerta B'
    assert values['postal_code']=='00100' and values['city']=='LOCALITA TEST'
    assert values['province']=='PROVINCIA TEST' and 'country' not in values
    assert row['PAIS']=='ITALIA' and row['DIRSIGLA']=='VIA'


def test_literal_sigla_and_no_country_inference():
    values=source_values(dict(DIRSIGLA='C',DIR='VIA SINTETICA',DIRNUM='12',TEL='+393331234567',IBAN='IT00'))
    assert values['address_line']=='C VIA SINTETICA 12' and 'country' not in values
    assert address_line({'DIRSIGLA':'PT','DIR':'CALLE TEST'})=='PT CALLE TEST'
    assert address_line({'DIRSIGLA':'C'}) is None


def test_source_projection_has_address_components():
    from backend.services.netfincas_source import COLUMNS
    for table in ('ALQ_INQUILINOS','ALQ_INQUILINOS_H'):
        assert {'DIRSIGLA','DIR','PAIS','CP','POB','PROVINCIA'}<=set(COLUMNS[table].split())
