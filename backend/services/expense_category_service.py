"""One catalogue for expenses and providers; IDs/codes survive every edit."""
import unicodedata
from uuid import uuid4

from sqlalchemy import select

from backend.models.owner_settlement import ExpenseCategory
from backend.services.financial_transaction import financial_transaction


def name_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(c))


class ExpenseCategoryService:
    def list(self, db, *, active_only=False):
        query = select(ExpenseCategory)
        if active_only:
            query = query.where(ExpenseCategory.active.is_(True))
        return list(db.scalars(query.order_by(ExpenseCategory.sort_order.asc().nulls_last(),
                                             ExpenseCategory.name, ExpenseCategory.id)))

    def save(self, db, category_id=None, *, name, description=None, sort_order=None, active=None):
        name = ' '.join((name or '').split())
        description = (description or '').strip() or None
        if not name or len(name) > 120:
            raise ValueError('Indique un nombre de categoría de hasta 120 caracteres.')
        if description and len(description) > 2000:
            raise ValueError('La descripción admite hasta 2000 caracteres.')
        try:
            order = int(sort_order) if sort_order not in (None, '') else None
        except (ValueError, TypeError):
            raise ValueError('El orden debe ser un número entero entre 0 y 999999.') from None
        if order is not None and not 0 <= order <= 999999:
            raise ValueError('El orden debe estar entre 0 y 999999.')
        # Serializes name checks and writes, including concurrent administrators.
        with financial_transaction(db):
            item = db.get(ExpenseCategory, category_id) if category_id is not None else ExpenseCategory(code='custom_' + uuid4().hex)
            if item is None:
                raise ValueError('Categoría no encontrada.')
            if any(c.id != category_id and name_key(c.name) == name_key(name) for c in self.list(db)):
                raise ValueError('Ya existe una categoría con ese nombre, activa o inactiva.')
            item.name, item.description, item.sort_order = name, description, order
            if active is not None:
                item.active = active
            elif category_id is None:
                item.active = True
            db.add(item)
        return item

    def set_active(self, db, category_id, active):
        with financial_transaction(db):
            item = db.get(ExpenseCategory, category_id)
            if item is None:
                raise ValueError('Categoría no encontrada.')
            item.active = active
        return item
