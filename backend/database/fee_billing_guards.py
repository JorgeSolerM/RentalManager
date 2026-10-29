"""SQLite append-only guards, also installed by the additive migration."""
from sqlalchemy import DDL, event

APPEND_ONLY = (
    'fee_obligations', 'fee_obligation_adjustments', 'fee_funds', 'fee_compensations',
    'fee_compensation_runs', 'management_fee_invoice_lines', 'management_fee_invoice_sources',
    'invoice_fiscal_records', 'fiscal_submission_attempts', 'invoice_rectification_notices',
)


def guard_statements():
    for table in APPEND_ONLY:
        for operation in ('UPDATE','DELETE'):
            yield (table, f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'Immutable billing history'); END")
    for operation in ('UPDATE','DELETE'):
        yield ('management_fee_invoices', f"CREATE TRIGGER IF NOT EXISTS immutable_issued_invoice_{operation.lower()} BEFORE {operation} ON management_fee_invoices WHEN OLD.status='issued' BEGIN SELECT RAISE(ABORT, 'Issued invoice is immutable'); END")
    yield ('invoice_series', "CREATE TRIGGER IF NOT EXISTS immutable_used_series BEFORE UPDATE ON invoice_series WHEN OLD.counter>0 AND (NEW.counter<OLD.counter OR NEW.prefix!=OLD.prefix OR NEW.issuer_id!=OLD.issuer_id OR NEW.padding!=OLD.padding OR NEW.document_type!=OLD.document_type OR NEW.fiscal_year IS NOT OLD.fiscal_year) BEGIN SELECT RAISE(ABORT, 'Used series identity is immutable'); END")


def register(metadata):
    for table,sql in guard_statements():
        event.listen(metadata.tables[table], 'after_create', DDL(sql).execute_if(dialect='sqlite'))
