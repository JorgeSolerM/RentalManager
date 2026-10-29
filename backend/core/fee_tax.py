"""Explicit tax configuration, not tax advice or automatic classification.

VAT only, general regime in this first profile. AEAT validation v1.2.2:
S2 requires explicit zero type/quota; exempt and N1/N2 omit both.
No fiscal default is inferred from a zero VAT rate.
"""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json

from backend.services.settlement_money import money

TREATMENTS = {
    'subject_taxable': 'IVA repercutido',
    'exempt': 'Exenta',
    'not_subject_location': 'No sujeta por localización',
    'not_subject_other': 'No sujeta por otra causa',
    'reverse_charge': 'Inversión del sujeto pasivo',
}
MAPPING_VERSION = 'aeat-v1.2.2-iva-general-v1'
ROUNDING_POLICY = 'per_source_cent_half_up_v1'


def tax_configuration(value):
    if not isinstance(value, dict):
        raise ValueError('Configure expresamente la fiscalidad del honorario.')
    required = {'tax_type', 'tax_regime', 'tax_treatment', 'vat_rate',
                'withholding_mode', 'withholding_rate', 'operation_date_policy'}
    if not required <= value.keys():
        raise ValueError('La configuración fiscal está incompleta.')
    for key, supported in (('currency', 'EUR'), ('rounding_policy', ROUNDING_POLICY),
                           ('tax_mapping_version', MAPPING_VERSION)):
        if key in value and value[key] != supported:
            raise ValueError('Versión, moneda o redondeo fiscal no soportado; no se transforma automáticamente.')
    if value['tax_type'] != 'IVA' or value['tax_regime'] != 'general':
        raise ValueError('Impuesto o régimen no soportado en esta fase.')
    treatment = value['tax_treatment']
    if treatment not in TREATMENTS:
        raise ValueError('Seleccione un tratamiento fiscal soportado.')
    rate, withholding = money(value['vat_rate']), money(value['withholding_rate'])
    if rate > 100 or withholding > 100:
        raise ValueError('Porcentaje fiscal fuera de rango.')
    # This is a deliberately narrow catalogue, not all historical VAT rates.
    if treatment == 'subject_taxable' and rate not in {Decimal('0'), Decimal('4'), Decimal('10'), Decimal('21')}:
        raise ValueError('Tipo de IVA no soportado para este perfil.')
    if treatment != 'subject_taxable' and rate != 0:
        raise ValueError('Este tratamiento no admite IVA repercutido.')
    mode = value['withholding_mode']
    if mode not in {'none', 'percentage'} or (mode == 'none' and withholding != 0) or (mode == 'percentage' and withholding == 0):
        raise ValueError('Revise el modo y porcentaje de retención.')
    reason = str(value.get('reason') or '').strip() or None
    legal = str(value.get('legal_reference') or '').strip() or None
    mention = str(value.get('legal_mention') or '').strip() or None
    if any(v and (len(v) > 500 or any(ord(c) < 32 for c in v)) for v in (reason, legal, mention)):
        raise ValueError('Referencia fiscal no válida.')
    if treatment == 'exempt' and reason not in {'E1', 'E4', 'E5', 'E6'}:
        raise ValueError('Seleccione una causa de exención compatible con régimen general.')
    if treatment != 'subject_taxable' and not all((reason, legal, mention)):
        raise ValueError('Informe motivo, referencia legal y mención de la operación.')
    if treatment == 'subject_taxable' and reason is not None:
        raise ValueError('El IVA repercutido no utiliza una causa de exención/no sujeción.')
    if value['operation_date_policy'] not in {'receipt_date', 'explicit'}:
        raise ValueError('Seleccione expresamente el criterio de fecha fiscal.')
    return dict(tax_type='IVA', tax_regime='general', tax_treatment=treatment,
                reason=reason, legal_reference=legal, legal_mention=mention,
                vat_rate=str(rate), withholding_mode=mode, withholding_rate=str(withholding),
                operation_date_policy=value['operation_date_policy'], currency='EUR',
                rounding_policy=ROUNDING_POLICY, tax_mapping_version=MAPPING_VERSION)


def fee_signature(terms, config, *, fee_base_policy='rent_collected_v1'):
    config = tax_configuration(config)
    if terms.fee_type != 'percentage_on_collected':
        raise ValueError('Tipo de honorario no soportado.')
    if terms.fixed_amount is not None or terms.minimum_amount is not None:
        raise ValueError('Honorarios fijos/mínimos todavía no operativos; requieren revisión.')
    if money(terms.vat_rate) != Decimal(config['vat_rate']) or money(terms.withholding_rate) != Decimal(config['withholding_rate']):
        raise ValueError('Las tasas no coinciden con las condiciones económicas.')
    if fee_base_policy != 'rent_collected_v1' or not 0 <= money(terms.percentage) <= 100:
        raise ValueError('Base o porcentaje de honorarios no soportado.')
    # Display wording is frozen separately. It must not split economically
    # identical groups merely because one administrator changed punctuation.
    signature_tax = {key: config[key] for key in (
        'tax_type', 'tax_regime', 'tax_treatment', 'vat_rate', 'withholding_mode',
        'withholding_rate', 'currency', 'rounding_policy', 'tax_mapping_version')}
    fields = dict(schema_version=1, fee_type=terms.fee_type, percentage=str(money(terms.percentage)),
                  fixed_amount=None, minimum_amount=None, fee_base_policy=fee_base_policy,
                  exemption_or_non_subject_reason=config['reason'], **signature_tax)
    # IDs, property names, dates of the terms and ownership shares are NOT included.
    canonical = json.dumps(fields, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return dict(fields=fields, digest=sha256(canonical.encode()).hexdigest())


def fiscal_snapshot(terms, config, row, receipt_date, *, operation_date=None, fee_base_policy='rent_collected_v1'):
    config = tax_configuration(config)
    if not isinstance(receipt_date, date):
        raise ValueError('Falta la fecha efectiva del cobro.')
    if config['operation_date_policy'] == 'receipt_date':
        if operation_date is not None and operation_date != receipt_date:
            raise ValueError('La fecha fiscal no coincide con el criterio configurado.')
        operation_date = receipt_date
    if not isinstance(operation_date, date):
        raise ValueError('Indique la fecha fiscal de operación; no se infiere del cierre.')
    base, vat, withholding, net = (money(row[k], signed=True) for k in
                                   ('fee_base', 'fee_vat', 'fee_withholding', 'fee'))
    if net != base + vat - withholding:
        raise ValueError('Importes congelados de honorarios incoherentes.')
    if config['tax_treatment'] != 'subject_taxable' and vat != 0:
        raise ValueError('El tratamiento no admite una cuota de IVA repercutida.')
    return dict(**config, fee_signature=fee_signature(terms, config, fee_base_policy=fee_base_policy),
                fee_base=str(base), fee_vat=str(vat), fee_withholding=str(withholding), fee_net=str(net),
                gross_invoice_total=str(base + vat), net_payable=str(net),
                operation_date=operation_date.isoformat(), receipt_date=receipt_date.isoformat(),
                economic_start=row.get('economic_start'), economic_end=row.get('economic_end'),
                property_id=row.get('property_id'), fee_terms_id=terms.id)


def verifactu_tax_detail(snapshot):
    """Return AEAT field values; copy stored amounts, never recalculate taxes."""
    config = tax_configuration(snapshot)
    base, vat = money(snapshot['fee_base'], signed=True), money(snapshot['fee_vat'], signed=True)
    treatment = config['tax_treatment']
    detail = dict(Impuesto='01', ClaveRegimen='01', BaseImponibleOimporteNoSujeto=str(base))
    if treatment == 'exempt':
        detail['OperacionExenta'] = config['reason']
    else:
        detail['CalificacionOperacion'] = {'subject_taxable':'S1', 'reverse_charge':'S2',
            'not_subject_other':'N1', 'not_subject_location':'N2'}[treatment]
    if treatment in {'subject_taxable', 'reverse_charge'}:
        detail.update(TipoImpositivo=config['vat_rate'], CuotaRepercutida=str(vat))
    if treatment != 'subject_taxable' and vat != 0:
        raise ValueError('Cuota incompatible con el tratamiento fiscal congelado.')
    return detail
