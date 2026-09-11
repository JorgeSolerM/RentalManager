import re
from sqlalchemy import select, or_
from backend.core.iban import normalize_iban, is_valid_iban
from backend.models.provider import Provider
from backend.models.owner_settlement import Expense, ExpenseCategory
from backend.services.financial_transaction import financial_transaction


class ProviderService:
    fields = {'legal_name':180, 'tax_id':40, 'address_line':255, 'postal_code':20,
              'city':120, 'province':120, 'country':2, 'phone':40, 'email':254, 'notes':4000}

    def list(self, db, search='', active_only=False):
        query = select(Provider)
        if active_only:
            query = query.where(Provider.active == True)
        if search.strip():
            term = '%' + search.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
            query = query.where(or_(Provider.legal_name.ilike(term, escape='\\'), Provider.tax_id.ilike(term, escape='\\'), Provider.email.ilike(term, escape='\\')))
        return list(db.scalars(query.order_by(Provider.legal_name, Provider.id)))

    def save(self, db, provider_id=None, **values):
        normalized = {}
        for field, limit in self.fields.items():
            value = ' '.join(str(values.get(field) or '').split()) or None
            if value and len(value) > limit:
                raise ValueError('Uno de los campos supera la longitud permitida.')
            normalized[field] = value
        if not normalized['legal_name']:
            raise ValueError('Indique el nombre o razón social del proveedor.')
        for field in ('tax_id','country'):
            if normalized[field]: normalized[field] = normalized[field].upper()
        if normalized['country'] and not re.fullmatch('[A-Z]{2}', normalized['country']):
            raise ValueError('Utilice un código de país de dos letras.')
        if normalized['email']:
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',normalized['email']):
                raise ValueError('Revise el email del proveedor.')
            normalized['email'] = normalized['email'].lower()
        iban = normalize_iban(values.get('iban'))
        if iban and not is_valid_iban(iban):
            raise ValueError('IBAN del proveedor no válido.')
        category_id = int(values['default_expense_category_id']) if values.get('default_expense_category_id') else None
        with financial_transaction(db):
            item = db.get(Provider, provider_id) if provider_id else Provider()
            if item is None: raise ValueError('Proveedor no encontrado.')
            if category_id:
                category = db.get(ExpenseCategory, category_id)
                if category is None or (not category.active and category_id != item.default_expense_category_id):
                    raise ValueError('Categoría habitual no disponible.')
            for key,value in normalized.items(): setattr(item,key,value)
            item.iban, item.default_expense_category_id = iban, category_id
            item.active = bool(values.get('active',True))
            db.add(item)
        return item

    def set_active(self, db, provider_id, active):
        with financial_transaction(db):
            item = db.get(Provider, provider_id)
            if item is None: raise ValueError('Proveedor no encontrado.')
            item.active = active
        return item

    def delete(self, db, provider_id):
        with financial_transaction(db):
            item = db.get(Provider, provider_id)
            if item is None: raise ValueError('Proveedor no encontrado.')
            if db.scalar(select(Expense.id).where(Expense.provider_id == provider_id).limit(1)):
                raise ValueError('El proveedor tiene gastos relacionados. Puede desactivarlo, no eliminarlo.')
            db.delete(item)
