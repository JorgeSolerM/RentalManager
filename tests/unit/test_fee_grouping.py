from copy import deepcopy
from decimal import Decimal
import pytest

from backend.core.fee_grouping import group_fee_sources
from backend.core.fee_tax import fee_signature
from tests.unit.test_fee_foundations import config, terms


def income(key, property_id, percentage='20', terms_id=1):
    return dict(key=key, owner_id=1, kind='income', property_id=property_id, date='2026-09-10',
        fiscal_snapshot=dict(fee_signature=fee_signature(terms(id=terms_id, percentage=Decimal(percentage)), config())))


def expense():
    return dict(key='expense:1', owner_id=1, kind='expense', property_id=1, date='2026-09-15')


def test_homogeneous_different_terms_ids_group_with_property_lines_preserved():
    sources = [income('income:1', 1), income('income:2', 2, terms_id=99)]
    original = deepcopy(sources)
    result = group_fee_sources(1, sources)
    assert not result['issues'] and len(result['groups']) == 1
    assert result['groups'][0]['property_ids'] == [1, 2]
    assert len(result['groups'][0]['sources']) == 2
    assert sources == original


def test_historical_different_rates_split_same_property_and_require_expense_choice():
    sources = [income('income:august', 1, '15'), income('income:september', 1), expense()]
    result = group_fee_sources(1, sources)
    assert len(result['groups']) == 2
    assert len(result['issues']) == 1 and len(result['issues'][0]['candidates']) == 2
    chosen = result['groups'][0]['group_key']
    decided = group_fee_sources(1, sources, {'expense:1': chosen})
    assert not decided['issues']
    assert sum(row['key'] == 'expense:1' for group in decided['groups'] for row in group['sources']) == 1


def test_unambiguous_expense_auto_assigned_and_order_stable():
    rows = [income('income:1', 1), income('income:2', 2, '15'), expense()]
    result = group_fee_sources(1, rows)
    assert result == group_fee_sources(1, reversed(rows))
    assert not result['issues']
    assert sum(len(group['sources']) for group in result['groups']) == 3


def test_unknown_assignment_and_mixed_owner_and_duplicate_rejected():
    row = income('income:1', 1)
    for rows, assignments in (([row, row], {}), ([{**row, 'owner_id': 2}], {}),
                              ([row], {'expense:999': 'not_a_group'})):
        with pytest.raises(ValueError):
            group_fee_sources(1, rows, assignments)


def test_expense_without_income_requires_configuration_not_silent_assignment():
    result = group_fee_sources(1, [expense()])
    assert not result['groups'] and len(result['issues']) == 1


def test_expense_only_and_non_fee_income_use_explicit_property_signature():
    signature = fee_signature(terms(), config())
    non_fee = dict(key='income:utilities', owner_id=1, kind='income', property_id=1,
                   date='2026-09-12', source_id=7)
    result = group_fee_sources(1, [expense(), non_fee], property_signatures={1: signature})
    assert not result['issues'] and len(result['groups']) == 1
    assert {r['key'] for r in result['groups'][0]['sources']} == {'income:utilities', 'expense:1'}


def test_invalid_signature_is_rejected_before_assignment():
    row = income('income:1', 1)
    row['fiscal_snapshot']['fee_signature']['fields']['percentage'] = '99.00'
    with pytest.raises(ValueError, match='firma fiscal'):
        group_fee_sources(1, [row])
