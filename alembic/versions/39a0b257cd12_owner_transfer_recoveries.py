"""Immutable effective recoveries on the economic branch."""
from alembic import op
import sqlalchemy as sa
revision='39a0b257cd12'
down_revision='289fa146bc01'
branch_labels=None
depends_on=None
TABLES=('owner_transfer_recoveries', 'owner_recovery_attributions', 'owner_recovery_return_links', 'owner_bank_credit_identities', 'owner_payout_reviews')
DDL=['\nCREATE TABLE owner_transfer_recoveries (\n\tid INTEGER NOT NULL, \n\tincident_id INTEGER NOT NULL, \n\tamount NUMERIC(12, 2) NOT NULL, \n\teffective_date DATE NOT NULL, \n\treceiving_account_hash VARCHAR(64) NOT NULL, \n\treceiving_account_suffix VARCHAR(4) NOT NULL, \n\tbank_reference VARCHAR(255) NOT NULL, \n\tbank_transaction_id VARCHAR(160), \n\treason TEXT NOT NULL, \n\tevidence TEXT NOT NULL, \n\treceived BOOLEAN NOT NULL, \n\toperator_id VARCHAR(160), \n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n\trequest_key VARCHAR(36) NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\treviewed_state VARCHAR(64) NOT NULL, \n\tallocations JSON NOT NULL, \n\timpact JSON NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (amount>0), \n\tCHECK (received=1), \n\tCHECK (length(trim(reason))>0 AND length(trim(evidence))>0 AND length(trim(bank_reference))>0), \n\tFOREIGN KEY(incident_id) REFERENCES owner_transfer_incidents (id) ON DELETE RESTRICT, \n\tUNIQUE (request_key)\n)\n\n', 'CREATE INDEX ix_owner_transfer_recoveries_incident_id ON owner_transfer_recoveries (incident_id)', '\nCREATE TABLE owner_recovery_attributions (\n\tid INTEGER NOT NULL, \n\trecovery_id INTEGER NOT NULL, \n\tallocations JSON NOT NULL, \n\treason TEXT NOT NULL, \n\toperator_id VARCHAR(160), \n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n\trequest_key VARCHAR(36) NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\treviewed_state VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (recovery_id), \n\tFOREIGN KEY(recovery_id) REFERENCES owner_transfer_recoveries (id) ON DELETE RESTRICT, \n\tUNIQUE (request_key)\n)\n\n', '\nCREATE TABLE owner_recovery_return_links (\n\tid INTEGER NOT NULL, \n\tincident_id INTEGER NOT NULL, \n\treturn_id INTEGER NOT NULL, \n\treason TEXT NOT NULL, \n\toperator_id VARCHAR(160), \n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n\trequest_key VARCHAR(36) NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\treviewed_state VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(incident_id) REFERENCES owner_transfer_incidents (id) ON DELETE RESTRICT, \n\tUNIQUE (return_id), \n\tFOREIGN KEY(return_id) REFERENCES owner_payout_returns (id) ON DELETE RESTRICT, \n\tUNIQUE (request_key)\n)\n\n', '\nCREATE TABLE owner_bank_credit_identities (\n\tid INTEGER NOT NULL, \n\treturn_id INTEGER, \n\trecovery_id INTEGER, \n\tbank_key VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK ((return_id IS NULL AND recovery_id IS NOT NULL) OR (return_id IS NOT NULL AND recovery_id IS NULL)), \n\tUNIQUE (return_id), \n\tFOREIGN KEY(return_id) REFERENCES owner_payout_returns (id) ON DELETE RESTRICT, \n\tUNIQUE (recovery_id), \n\tFOREIGN KEY(recovery_id) REFERENCES owner_transfer_recoveries (id) ON DELETE RESTRICT, \n\tUNIQUE (bank_key)\n)\n\n', '\nCREATE TABLE owner_payout_reviews (\n\tid INTEGER NOT NULL, \n\tpayout_id INTEGER NOT NULL, \n\treason TEXT NOT NULL, \n\toperator_id VARCHAR(160), \n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\treviewed_state VARCHAR(64) NOT NULL, \n\t"values" JSON NOT NULL, \n\timpact JSON NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (payout_id), \n\tFOREIGN KEY(payout_id) REFERENCES owner_payouts (id) ON DELETE RESTRICT\n)\n\n']


def upgrade():
    for sql in DDL:op.execute(sql)
    for table in TABLES:
        for action in ('update','delete'):
            op.execute(f"CREATE TRIGGER {table}_no_{action} BEFORE {action.upper()} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_recovery_history'); END")
    op.execute("""CREATE TRIGGER recovery_within_incident BEFORE INSERT ON owner_transfer_recoveries
      WHEN NOT EXISTS(SELECT 1 FROM owner_transfer_incidents i WHERE i.id=NEW.incident_id
        AND ROUND(NEW.amount+COALESCE((SELECT SUM(r.amount) FROM owner_transfer_recoveries r WHERE r.incident_id=i.id),0),2)<=i.affected_amount)
      BEGIN SELECT RAISE(ABORT,'recovery_exceeds_incident'); END""")
    for table,other in [('owner_transfer_recoveries','owner_payout_returns'),('owner_payout_returns','owner_transfer_recoveries')]:
        op.execute(f"""CREATE TRIGGER {table}_cross_credit_duplicate BEFORE INSERT ON {table}
          WHEN EXISTS(SELECT 1 FROM {other} r WHERE r.receiving_account_hash=NEW.receiving_account_hash AND
            ((NEW.bank_transaction_id IS NOT NULL AND UPPER(r.bank_transaction_id)=UPPER(NEW.bank_transaction_id)) OR
             (r.effective_date=NEW.effective_date AND r.amount=NEW.amount AND (NULLIF(r.bank_transaction_id,'') IS NULL OR NULLIF(NEW.bank_transaction_id,'') IS NULL))))
          OR EXISTS(SELECT 1 FROM {table} r WHERE r.receiving_account_hash=NEW.receiving_account_hash AND
            ((NEW.bank_transaction_id IS NOT NULL AND UPPER(r.bank_transaction_id)=UPPER(NEW.bank_transaction_id)) OR
             (r.effective_date=NEW.effective_date AND r.amount=NEW.amount AND (NULLIF(r.bank_transaction_id,'') IS NULL OR NULLIF(NEW.bank_transaction_id,'') IS NULL))))
          BEGIN SELECT RAISE(ABORT,'duplicate_bank_credit'); END""")
    op.execute("""CREATE TRIGGER recovery_link_matches_transfer BEFORE INSERT ON owner_recovery_return_links
      WHEN NOT EXISTS(SELECT 1 FROM owner_transfer_incidents i JOIN owner_payout_returns r ON r.transfer_root_id=i.payout_root_id WHERE i.id=NEW.incident_id AND r.id=NEW.return_id)
      BEGIN SELECT RAISE(ABORT,'invalid_documentary_return_link'); END""")
    # Validate conservation and original ownership for both immediate and later allocation.
    for table in ('owner_transfer_recoveries','owner_recovery_attributions'):
        inc='NEW.incident_id' if table=='owner_transfer_recoveries' else '(SELECT incident_id FROM owner_transfer_recoveries WHERE id=NEW.recovery_id)'
        amount='NEW.amount' if table=='owner_transfer_recoveries' else '(SELECT amount FROM owner_transfer_recoveries WHERE id=NEW.recovery_id)'
        exclude='-1' if table=='owner_transfer_recoveries' else 'NEW.recovery_id'
        original=f"(SELECT after_state FROM owner_transfer_incident_operations WHERE incident_id={inc} ORDER BY CASE kind WHEN 'attribute' THEN 1 ELSE 0 END DESC LIMIT 1)"
        pending="0" if table=='owner_transfer_recoveries' else "EXISTS(SELECT 1 FROM owner_transfer_recoveries r,json_each(r.allocations) WHERE r.id=NEW.recovery_id) OR NOT EXISTS(SELECT 1 FROM json_each(NEW.allocations))"
        op.execute(f"""CREATE TRIGGER {table}_valid_allocation BEFORE INSERT ON {table}
          WHEN json_type(NEW.allocations) IS NOT 'object' OR ({pending})
          OR (EXISTS(SELECT 1 FROM json_each(NEW.allocations)) AND ROUND((SELECT SUM(CAST(value AS NUMERIC)) FROM json_each(NEW.allocations)),2)!={amount})
          OR EXISTS(SELECT 1 FROM json_each(NEW.allocations) a WHERE CAST(a.value AS NUMERIC)<=0
            OR NOT EXISTS(SELECT 1 FROM json_each({original},'$.allocations') o WHERE o.key=a.key)
            OR ROUND(CAST(a.value AS NUMERIC)+COALESCE((SELECT SUM(CAST(v.value AS NUMERIC)) FROM owner_transfer_recoveries r
               JOIN json_each(COALESCE((SELECT allocations FROM owner_recovery_attributions WHERE recovery_id=r.id),r.allocations)) v
               WHERE r.incident_id={inc} AND r.id!={exclude} AND v.key=a.key),0),2)>
               CAST((SELECT value FROM json_each({original},'$.allocations') o WHERE o.key=a.key) AS NUMERIC))
          BEGIN SELECT RAISE(ABORT,'invalid_recovery_allocation'); END""")


def downgrade():
    if any(op.get_bind().execute(sa.text('SELECT COUNT(*) FROM '+t)).scalar() for t in TABLES):raise RuntimeError('No se elimina historial de recuperaciones.')
    for name in ('recovery_within_incident','owner_transfer_recoveries_cross_credit_duplicate','owner_payout_returns_cross_credit_duplicate','recovery_link_matches_transfer','owner_transfer_recoveries_valid_allocation','owner_recovery_attributions_valid_allocation'):
        op.execute('DROP TRIGGER IF EXISTS '+name)
    for table in reversed(TABLES):
        for action in ('update','delete'):op.execute(f'DROP TRIGGER {table}_no_{action}')
        op.drop_table(table)
