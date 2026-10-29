from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from backend.core.fee_compensation import Obligation, compensation_plan
from backend.core.fee_tax import fee_signature, fiscal_snapshot, tax_configuration, verifactu_tax_detail


def config(**overrides):
    return dict(tax_type='IVA', tax_regime='general', tax_treatment='subject_taxable',
                vat_rate='21', withholding_mode='percentage', withholding_rate='15',
                operation_date_policy='receipt_date', **overrides)


def terms(**overrides):
    values = dict(id=1, fee_type='percentage_on_collected', percentage=D('20'),
                  fixed_amount=None, minimum_amount=None, vat_rate=D('21'), withholding_rate=D('15'))
    values.update(overrides)
    return SimpleNamespace(**values)


def obligation(key, kind, amount, paid='0', day=1, owner=1):
    return Obligation(key, owner, kind, date(2026, 9, day), D(amount), D(paid))


def test_partial_priority_and_later_funds_do_not_create_new_debt():
    rows = [obligation('fee', 'management_fee', '60'), obligation('expense', 'expense_advance', '500')]
    first = compensation_plan(1, '300', rows)
    assert first == dict(applications=[dict(obligation_key='expense', amount='300.00')],
                         available='0.00', pending='260.00')
    second = compensation_plan(1, '500', [rows[0], obligation('expense', 'expense_advance', '500', '300')])
    assert second == dict(applications=[dict(obligation_key='expense', amount='200.00'),
                                       dict(obligation_key='fee', amount='60.00')],
                          available='240.00', pending='0.00')
    assert rows[1].compensated == 0  # pure preview, no mutation


def test_older_fee_precedes_newer_expense_and_ties_are_stable():
    rows = [obligation('b', 'expense_advance', '100', day=2),
            obligation('a', 'expense_advance', '100', day=2),
            obligation('fee', 'management_fee', '50')]
    result = compensation_plan(1, '175', rows)
    assert result == compensation_plan(1, '175', reversed(rows))
    assert result['applications'] == [dict(obligation_key='fee', amount='50.00'),
                                      dict(obligation_key='a', amount='100.00'),
                                      dict(obligation_key='b', amount='25.00')]


@pytest.mark.parametrize('rows', [
    [obligation('a', 'expense_advance', '100', owner=2)],
    [obligation('a', 'expense_advance', '100', '101')],
    [obligation('a', 'expense_advance', '-100')],
    [obligation('a', 'wrong', '100')],
    [obligation('a', 'expense_advance', '100')] * 2,
])
def test_invalid_compensation_is_rejected(rows):
    with pytest.raises(ValueError):
        compensation_plan(1, '100', rows)


def test_fee_signature_compares_content_not_ids_or_display_wording():
    first = fee_signature(terms(), config())
    same = fee_signature(terms(id=99), {**config(), 'legal_mention': 'Texto descriptivo'})
    assert first == same
    assert first != fee_signature(terms(percentage=D('15')), config())
    assert 'id' not in first['fields'] and 'fee_terms_id' not in first['fields']


def test_tax_snapshot_preserves_three_dates_and_gross_net():
    row = dict(fee_base='304', fee_vat='63.84', fee_withholding='45.60', fee='322.24',
               economic_start='2026-08-01', economic_end='2026-09-01', property_id=1)
    snapshot = fiscal_snapshot(terms(), config(), row, date(2026, 9, 10))
    assert snapshot['gross_invoice_total'] == '367.84'
    assert snapshot['net_payable'] == '322.24'
    assert snapshot['economic_start'] == '2026-08-01'
    assert snapshot['receipt_date'] == snapshot['operation_date'] == '2026-09-10'
    explicit = {**config(), 'operation_date_policy': 'explicit'}
    with pytest.raises(ValueError, match='fecha fiscal'):
        fiscal_snapshot(terms(), explicit, row, date(2026, 9, 10))
    other = fiscal_snapshot(terms(), explicit, row, date(2026, 9, 10), operation_date=date(2026, 9, 30))
    assert other['operation_date'] == '2026-09-30'
    assert verifactu_tax_detail(snapshot)['CuotaRepercutida'] == '63.84'


@pytest.mark.parametrize('treatment,reason,code', [
    ('exempt', 'E1', 'E1'), ('not_subject_location', 'localizacion', 'N2'),
    ('not_subject_other', 'causa_configurada', 'N1'), ('reverse_charge', 'inversion', 'S2')])
def test_explicit_nonordinary_tax_mapping(treatment, reason, code):
    cfg = {**config(), 'tax_treatment': treatment, 'reason': reason, 'vat_rate': '0',
           'legal_reference': 'Referencia de prueba', 'legal_mention': 'Mención de prueba'}
    frozen = fiscal_snapshot(terms(vat_rate=D('0')), cfg,
        dict(fee_base='100', fee_vat='0', fee_withholding='15', fee='85'), date(2026, 9, 1))
    detail = verifactu_tax_detail(frozen)
    assert detail.get('OperacionExenta', detail.get('CalificacionOperacion')) == code
    assert ('TipoImpositivo' in detail) == (code == 'S2')


@pytest.mark.parametrize('change', [
    {'tax_type': 'IGIC'}, {'tax_type': 'IPSI'}, {'tax_regime': 'special'},
    {'tax_treatment': 'exempt'}, {'vat_rate': '-1'}, {'vat_rate': '5'},
    {'withholding_mode': 'none'}, {'operation_date_policy': 'closing'},
    {'tax_treatment': 'not_subject_other'},
])
def test_no_tax_inference_or_unsupported_fallback(change):
    with pytest.raises(ValueError):
        tax_configuration({**config(), **change})


def test_zero_vat_does_not_mean_exempt():
    cfg = {**config(), 'vat_rate': '0'}
    assert tax_configuration(cfg)['tax_treatment'] == 'subject_taxable'
    with pytest.raises(ValueError):
        tax_configuration({'vat_rate': '0'})
