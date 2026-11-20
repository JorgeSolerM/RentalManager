"""Add immutable transfer incidents on the economic branch only."""
from alembic import op
import sqlalchemy as sa
revision='289fa146bc01'
down_revision='178e9035abf0'
branch_labels=None
depends_on=None
TABLES=('owner_transfer_incidents','owner_transfer_outflows','owner_transfer_incident_operations','owner_transfer_identities')
DDL=["\nCREATE TABLE owner_transfer_incidents (\n\tid INTEGER NOT NULL, \n\tsettlement_id INTEGER NOT NULL, \n\tintended_owner_id INTEGER NOT NULL, \n\tsource_kind VARCHAR(20) NOT NULL, \n\tpayout_root_id INTEGER, \n\tduplicate_of_root_id INTEGER, \n\tkind VARCHAR(24) NOT NULL, \n\taffected_amount NUMERIC(12, 2) NOT NULL, \n\trecipient_owner_id INTEGER, \n\trecipient_description VARCHAR(180), \n\treceipt_accredited BOOLEAN NOT NULL, \n\treason TEXT NOT NULL, \n\tevidence TEXT NOT NULL, \n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_transfer_incident_kind CHECK (kind IN ('wrong_account','wrong_recipient','unknown_recipient','duplicate')), \n\tCONSTRAINT ck_transfer_incident_source CHECK (source_kind IN ('payout','extraordinary')), \n\tCONSTRAINT ck_transfer_incident_link CHECK ((source_kind='payout' AND payout_root_id IS NOT NULL) OR (source_kind='extraordinary' AND payout_root_id IS NULL)), \n\tCONSTRAINT ck_transfer_incident_amount CHECK (affected_amount>0), \n\tCONSTRAINT ck_transfer_incident_evidence CHECK (length(trim(reason))>0 AND length(trim(evidence))>0), \n\tFOREIGN KEY(settlement_id) REFERENCES owner_settlements (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(intended_owner_id) REFERENCES owners (id) ON DELETE RESTRICT, \n\tUNIQUE (payout_root_id), \n\tFOREIGN KEY(payout_root_id) REFERENCES owner_payouts (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(duplicate_of_root_id) REFERENCES owner_payouts (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(recipient_owner_id) REFERENCES owners (id) ON DELETE RESTRICT\n)\n\n", '\nCREATE TABLE owner_transfer_outflows (\n\tid INTEGER NOT NULL, \n\tincident_id INTEGER NOT NULL, \n\tamount NUMERIC(12, 2) NOT NULL, \n\teffective_date DATE NOT NULL, \n\tsource_account_hash VARCHAR(64), \n\tsource_account_suffix VARCHAR(4), \n\tdestination_hash VARCHAR(64), \n\tdestination_suffix VARCHAR(4), \n\treference VARCHAR(255) NOT NULL, \n\tbank_transaction_id VARCHAR(160), \n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_transfer_outflow_amount CHECK (amount>0), \n\tUNIQUE (incident_id), \n\tFOREIGN KEY(incident_id) REFERENCES owner_transfer_incidents (id) ON DELETE RESTRICT\n)\n\n', "\nCREATE TABLE owner_transfer_incident_operations (\n\trequest_key VARCHAR(36) NOT NULL, \n\tincident_id INTEGER NOT NULL, \n\tkind VARCHAR(16) NOT NULL, \n\treason TEXT NOT NULL, \n\toperator_id VARCHAR(160), \n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n\tbefore_state JSON NOT NULL, \n\tafter_state JSON NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\treviewed_state VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (request_key), \n\tCONSTRAINT ck_transfer_incident_operation CHECK (kind IN ('register','attribute')), \n\tCONSTRAINT uq_incident_operation_kind UNIQUE (incident_id, kind), \n\tFOREIGN KEY(incident_id) REFERENCES owner_transfer_incidents (id) ON DELETE RESTRICT\n)\n\n", '\nCREATE TABLE owner_transfer_identities (\n\tid INTEGER NOT NULL, \n\tpayout_root_id INTEGER, \n\toutflow_id INTEGER, \n\tbank_key VARCHAR(64) NOT NULL, \n\tsource_account_hash VARCHAR(64), \n\tbank_transaction_id VARCHAR(160), \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_transfer_identity_source CHECK ((payout_root_id IS NOT NULL AND outflow_id IS NULL) OR (payout_root_id IS NULL AND outflow_id IS NOT NULL)), \n\tUNIQUE (payout_root_id), \n\tFOREIGN KEY(payout_root_id) REFERENCES owner_payouts (id) ON DELETE RESTRICT, \n\tUNIQUE (outflow_id), \n\tFOREIGN KEY(outflow_id) REFERENCES owner_transfer_outflows (id) ON DELETE RESTRICT, \n\tUNIQUE (bank_key)\n)\n\n', 'CREATE INDEX ix_owner_transfer_incidents_settlement_id ON owner_transfer_incidents (settlement_id)', 'CREATE INDEX ix_owner_transfer_incidents_intended_owner_id ON owner_transfer_incidents (intended_owner_id)', 'CREATE INDEX ix_owner_transfer_incident_operations_incident_id ON owner_transfer_incident_operations (incident_id)']

def upgrade():
    for sql in DDL:op.execute(sql)
    for table in TABLES:
        for action in ('update','delete'):
            op.execute(f"CREATE TRIGGER {table}_no_{action} BEFORE {action.upper()} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_transfer_history'); END")
    op.execute("""CREATE TRIGGER transfer_incident_valid_source BEFORE INSERT ON owner_transfer_incidents
      WHEN NOT EXISTS(SELECT 1 FROM owner_settlements s WHERE s.id=NEW.settlement_id AND s.owner_id=NEW.intended_owner_id AND s.status='closed')
      OR (NEW.source_kind='payout' AND EXISTS(SELECT 1 FROM owner_payout_correction_operations WHERE replacement_payout_id=NEW.payout_root_id))
      OR (NEW.source_kind='payout' AND NOT EXISTS(
        WITH RECURSIVE chain(id) AS (SELECT NEW.payout_root_id UNION ALL SELECT o.replacement_payout_id FROM owner_payout_correction_operations o JOIN chain c ON o.original_payout_id=c.id WHERE o.replacement_payout_id IS NOT NULL)
        SELECT 1 FROM chain JOIN owner_payouts p ON p.id=chain.id WHERE p.settlement_id=NEW.settlement_id AND p.owner_id=NEW.intended_owner_id
        AND NOT EXISTS(SELECT 1 FROM owner_payout_correction_operations o WHERE o.original_payout_id=p.id)
        AND NEW.affected_amount<=ROUND(p.amount-COALESCE((SELECT SUM(r.amount) FROM owner_payout_returns r WHERE r.transfer_root_id=NEW.payout_root_id),0),2)))
      BEGIN SELECT RAISE(ABORT,'invalid_transfer_incident'); END""")
    op.execute("""CREATE TRIGGER transfer_outflow_matches_incident BEFORE INSERT ON owner_transfer_outflows
      WHEN NOT EXISTS(SELECT 1 FROM owner_transfer_incidents i WHERE i.id=NEW.incident_id AND i.source_kind='extraordinary' AND i.affected_amount=NEW.amount)
      BEGIN SELECT RAISE(ABORT,'invalid_extraordinary_outflow'); END""")
    op.execute("""CREATE TRIGGER transfer_incident_blocks_correction BEFORE INSERT ON owner_payout_correction_operations
      WHEN EXISTS(WITH RECURSIVE chain(id) AS (SELECT payout_root_id FROM owner_transfer_incidents WHERE payout_root_id IS NOT NULL UNION ALL SELECT o.replacement_payout_id FROM owner_payout_correction_operations o JOIN chain c ON o.original_payout_id=c.id WHERE o.replacement_payout_id IS NOT NULL) SELECT 1 FROM chain WHERE id=NEW.original_payout_id)
      BEGIN SELECT RAISE(ABORT,'transfer_incident_requires_specific_workflow'); END""")
    op.execute("""CREATE TRIGGER transfer_incident_blocks_return BEFORE INSERT ON owner_payout_returns
      WHEN EXISTS(SELECT 1 FROM owner_transfer_incidents WHERE payout_root_id=NEW.transfer_root_id)
      BEGIN SELECT RAISE(ABORT,'transfer_incident_requires_recovery_workflow'); END""")
    op.execute("""CREATE TRIGGER transfer_operation_valid_attribution BEFORE INSERT ON owner_transfer_incident_operations
      WHEN json_type(NEW.after_state,'$.allocations')!='object'
      OR (EXISTS(SELECT 1 FROM json_each(NEW.after_state,'$.allocations')) AND ROUND((SELECT SUM(CAST(value AS NUMERIC)) FROM json_each(NEW.after_state,'$.allocations')),2)!=(SELECT affected_amount FROM owner_transfer_incidents WHERE id=NEW.incident_id))
      OR EXISTS(SELECT 1 FROM json_each(NEW.after_state,'$.allocations') a WHERE CAST(a.value AS NUMERIC)<=0 OR NOT EXISTS(SELECT 1 FROM owners WHERE id=CAST(a.key AS INTEGER)))
      OR (NEW.kind='attribute' AND (NOT EXISTS(SELECT 1 FROM owner_transfer_incidents i WHERE i.id=NEW.incident_id AND i.source_kind='extraordinary') OR NOT EXISTS(SELECT 1 FROM owner_transfer_incident_operations o WHERE o.incident_id=NEW.incident_id AND o.kind='register' AND NOT EXISTS(SELECT 1 FROM json_each(o.after_state,'$.allocations'))) OR NOT EXISTS(SELECT 1 FROM json_each(NEW.after_state,'$.allocations'))))
      BEGIN SELECT RAISE(ABORT,'invalid_transfer_attribution'); END""")
    if sa.inspect(op.get_bind()).has_table('fee_compensations'):
        op.execute("""CREATE TRIGGER transfer_incident_blocks_compensation BEFORE INSERT ON fee_compensations
          WHEN EXISTS(SELECT 1 FROM owner_transfer_incidents WHERE settlement_id=NEW.settlement_id)
          BEGIN SELECT RAISE(ABORT,'transfer_incident_blocks_compensation'); END""")

def downgrade():
    if any(op.get_bind().execute(sa.text('SELECT COUNT(*) FROM '+t)).scalar() for t in TABLES):raise RuntimeError('No se elimina historial de incidencias.')
    for name in ('transfer_operation_valid_attribution','transfer_incident_valid_source','transfer_outflow_matches_incident','transfer_incident_blocks_correction','transfer_incident_blocks_return','transfer_incident_blocks_compensation'):
        op.execute('DROP TRIGGER IF EXISTS '+name)
    for table in reversed(TABLES):
        for action in ('update','delete'):op.execute(f'DROP TRIGGER {table}_no_{action}')
        op.drop_table(table)
