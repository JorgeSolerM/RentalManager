"""Private, versioned PDF artifacts. Never recalculates a closed settlement."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import uuid4

import portalocker
from sqlalchemy import select

from backend.core.config import get_public_site_name, get_public_contact_config
from backend.database.session import DATABASE_PATH
from backend.models import Booking, Owner, Property, PaymentAllocation
from backend.models.owner_settlement import OwnerSettlement, OwnerSettlementLine, OwnerPayout, ExpensePayment


def document_identity(db, settlement, rows):
    owner = db.get(Owner, settlement.owner_id)
    contact = get_public_contact_config()
    property_ids = settlement.selection['properties']
    properties = {str(p.id): p.name for p in db.scalars(select(Property).where(Property.id.in_(property_ids)))}
    references = {}
    for row in rows:
        extra = {}
        if row['kind'] == 'income':
            allocation = db.get(PaymentAllocation, row['source_id'])
            booking = db.get(Booking, allocation.charge.booking_id)
            people = {p.person_id: p.person.display_name or p.person.full_name for p in booking.parties
                      if p.role in ('tenant', 'occupant')}
            extra['tenant'] = ', '.join(people.values()) or booking.source_guest_name or 'No identificado'
        elif row['kind'] == 'expense':
            payment = db.get(ExpensePayment, row['source_id'])
            extra['reference'] = payment.reference or ''
        references[row['key']] = extra
    return dict(issuer=get_public_site_name(), manager=contact.name, email=contact.email,
                owner=owner.name, properties=properties, references=references)


def storage_for(db):
    database = Path(db.get_bind().url.database).resolve()
    if database == DATABASE_PATH.resolve():
        return DATABASE_PATH.parent / 'finance' / 'settlements'
    return database.parent / (database.stem + '_settlement_documents')


class SettlementDocumentService:
    def __init__(self, storage):
        self.storage = Path(storage).resolve()

    def _directory(self, settlement_id):
        if not isinstance(settlement_id, int) or settlement_id <= 0:
            raise ValueError('Liquidación no válida.')
        return self.storage / str(settlement_id)

    def _read(self, folder, manifest):
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if not re.fullmatch(r'liquidacion-[0-9]+-v[0-9]+-[a-f0-9]{32}\.pdf', data['filename']):
            raise ValueError('Nombre de documento no válido.')
        path = folder / data['filename']
        if path.resolve().parent != folder.resolve() or not path.is_file():
            raise ValueError('Documento no disponible.')
        if sha256(path.read_bytes()).hexdigest() != data['sha256']:
            raise ValueError('Integridad del documento no válida.')
        return data, path

    def download(self, db, settlement_id, version):
        item = db.get(OwnerSettlement, settlement_id)
        if item is None or item.status != 'closed' or version < 1:
            raise ValueError('Documento no disponible para esta liquidación.')
        folder = self._directory(settlement_id)
        manifest = folder / f'v{version}.json'
        if not manifest.is_file():
            raise ValueError('Documento no encontrado.')
        return self._read(folder, manifest)

    def generate(self, db, settlement_id):
        item = db.get(OwnerSettlement, settlement_id)
        if item is None or item.status != 'closed':
            raise ValueError('Solo las liquidaciones cerradas admiten PDF definitivo.')
        folder = self._directory(settlement_id)
        folder.mkdir(parents=True, exist_ok=True)
        with portalocker.Lock(str(folder / '.lock'), timeout=15):
            manifests = sorted(folder.glob('v*.json'), key=lambda p: int(p.stem[1:]))
            previous = [self._read(folder, p)[0] for p in manifests]
            lines = list(db.scalars(select(OwnerSettlementLine).where(
                OwnerSettlementLine.settlement_id == item.id).order_by(OwnerSettlementLine.id)))
            rows = [deepcopy(line.snapshot) for line in lines]
            # Never serialize the other co-owners' distribution into this artifact.
            for row in rows:
                row.pop('distribution', None)
            header = deepcopy(item.snapshot.get('document_identity'))
            legacy = header is None
            if legacy:
                header = previous[0]['identity'] if previous else document_identity(db, item, rows)
            payouts = list(db.scalars(select(OwnerPayout).where(OwnerPayout.settlement_id == item.id).order_by(OwnerPayout.id)))
            payout_rows = [dict(id=p.id, date=str(p.effective_date), amount=str(p.amount),
                                account_suffix=(p.account_snapshot.get('iban') or '')[-4:]) for p in payouts]
            paid = sum((p.amount for p in payouts), Decimal('0.00'))
            payload = dict(id=item.id, owner_id=item.owner_id, identity=header, legacy_identity=legacy,
                           start=str(item.period_start), end=str(item.period_end), closed_at=str(item.closed_at),
                           rows=rows, totals=item.snapshot['totals'], payouts=payout_rows, paid=str(paid),
                           pending=str(max(Decimal('0.00'), Decimal(item.snapshot['totals']['payout_due'])-paid)))
            digest = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            from backend.services.settlement_pdf import render_settlement_pdf, RENDERER_VERSION
            for artifact in previous:
                if artifact['source_sha256'] == digest and artifact.get('renderer_version', 1) == RENDERER_VERSION:
                    return artifact
            generated = datetime.now(timezone.utc).isoformat()
            content = render_settlement_pdf(payload, generated)
            version = max((p['version'] for p in previous), default=0) + 1
            name = f'liquidacion-{item.id}-v{version}-{uuid4().hex}.pdf'
            path = folder / name
            artifact = dict(settlement_id=item.id, type='settlement', version=version, filename=name,
                            generated_at=generated, sha256=sha256(content).hexdigest(), source_sha256=digest,
                            identity=header, format='PDF/A4', renderer_version=RENDERER_VERSION)
            manifest = folder / f'v{version}.json'
            temporary = folder / (uuid4().hex + '.tmp')
            try:
                with path.open('xb') as output:
                    output.write(content)
                temporary.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True), encoding='utf-8')
                temporary.replace(manifest)
            except Exception:
                path.unlink(missing_ok=True)
                temporary.unlink(missing_ok=True)
                raise
            return artifact
