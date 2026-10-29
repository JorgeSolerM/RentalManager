"""Fail-closed switches for the synthetic fee-invoicing checkpoint.

No transport, certificate access or real fiscal emission is provided here.
"""
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class InvoicingConfig:
    enabled: bool = False
    verifactu_enabled: bool = False
    submission_enabled: bool = False


def invoicing_config():
    def enabled(name):
        value = os.getenv(name, 'false').strip().lower()
        if value not in {'true', 'false', '1', '0'}:
            raise ValueError(f'{name}: valor booleano no válido.')
        return value in {'true', '1'}
    config = InvoicingConfig(enabled('INVOICING_ENABLED'), enabled('VERIFACTU_ENABLED'),
                            enabled('VERIFACTU_SUBMISSION_ENABLED'))
    if config.submission_enabled:
        raise ValueError('Los envíos a AEAT están deshabilitados durante este checkpoint.')
    if config.verifactu_enabled and not config.enabled:
        raise ValueError('VERI*FACTU requiere la facturación habilitada en el entorno de prueba.')
    return config


def require_synthetic_invoicing(db):
    """Enabling a flag alone must never permit issuing against production."""
    config = invoicing_config()
    if not config.enabled:
        raise ValueError('Facturación deshabilitada.')
    target = db.get_bind().url.database
    approved = os.getenv('INVOICING_SYNTHETIC_DATABASE', '').strip()
    if not target or not approved:
        raise ValueError('Configure expresamente una BD sintética aislada.')
    path, approved_path = Path(target).resolve(), Path(approved).resolve()
    real = Path(__file__).resolve().parents[2] / 'data' / 'RentalManager.db'
    if path != approved_path or path == real.resolve() or (path.exists() and real.exists() and path.samefile(real)):
        raise ValueError('La emisión de prueba no puede utilizar la BD real.')
    return config
