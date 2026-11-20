"""Add immutable loss recognition without banking effects."""
from alembic import op
import sqlalchemy as sa
revision='4ab1c368de23'
down_revision='39a0b257cd12'
branch_labels=None
depends_on=None
DDL=["\nCREATE TABLE owner_transfer_regularizations (\n\tid INTEGER NOT NULL, \n\tincident_id INTEGER NOT NULL, \n\tloss_id INTEGER, \n\tkind VARCHAR(20) NOT NULL, \n\tamount NUMERIC(12, 2) NOT NULL, \n\tresponsible VARCHAR(12) NOT NULL, \n\tresponsible_owner_id INTEGER, \n\tagreement TEXT NOT NULL, \n\treason TEXT NOT NULL, \n\tevidence TEXT NOT NULL, \n\tevidence_reference VARCHAR(160) NOT NULL, \n\trecognition_key VARCHAR(64), \n\toperator_id VARCHAR(160), \n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n\tbefore_state JSON NOT NULL, \n\tafter_state JSON NOT NULL, \n\trequest_key VARCHAR(36) NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\treviewed_state VARCHAR(64) NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (kind IN ('recognize','responsibility')), \n\tCHECK (amount > 0), \n\tCHECK (responsible IN ('pending','manager','owner')), \n\tCHECK ((kind='recognize' AND loss_id IS NULL) OR (kind='responsibility' AND loss_id IS NOT NULL AND responsible!='pending')), \n\tCHECK ((responsible='owner' AND responsible_owner_id IS NOT NULL AND length(trim(agreement))>0) OR (responsible!='owner' AND responsible_owner_id IS NULL)), \n\tCHECK (length(trim(reason))>0 AND length(trim(evidence))>0 AND length(trim(evidence_reference))>0), \n\tUNIQUE (incident_id, recognition_key), \n\tUNIQUE (loss_id), \n\tFOREIGN KEY(incident_id) REFERENCES owner_transfer_incidents (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(loss_id) REFERENCES owner_transfer_regularizations (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(responsible_owner_id) REFERENCES owners (id) ON DELETE RESTRICT, \n\tUNIQUE (request_key)\n)\n\n", 'CREATE INDEX ix_owner_transfer_regularizations_incident_id ON owner_transfer_regularizations (incident_id)']

def upgrade():
    for sql in DDL:op.execute(sql)
    for action in ('UPDATE','DELETE'):
        op.execute(f"CREATE TRIGGER regularization_no_{action.lower()} BEFORE {action} ON owner_transfer_regularizations BEGIN SELECT RAISE(ABORT,'immutable_regularization'); END")
    op.execute("""CREATE TRIGGER loss_recognition_limit BEFORE INSERT ON owner_transfer_regularizations WHEN NEW.kind='recognize' AND NOT EXISTS (
        SELECT 1 FROM owner_transfer_incidents i WHERE i.id=NEW.incident_id AND i.receipt_accredited=0 AND
        ROUND(NEW.amount+COALESCE((SELECT SUM(amount) FROM owner_transfer_regularizations l WHERE l.incident_id=i.id AND l.kind='recognize'),0)+COALESCE((SELECT SUM(amount) FROM owner_transfer_recoveries r WHERE r.incident_id=i.id),0),2)<=i.affected_amount
    ) BEGIN SELECT RAISE(ABORT,'loss_exceeds_unrecognized'); END""")
    op.execute("""CREATE TRIGGER loss_responsibility_parent BEFORE INSERT ON owner_transfer_regularizations WHEN NEW.kind='responsibility' AND NOT EXISTS (
        SELECT 1 FROM owner_transfer_regularizations p WHERE p.id=NEW.loss_id AND p.kind='recognize' AND p.incident_id=NEW.incident_id AND p.responsible='pending' AND p.amount=NEW.amount
    ) BEGIN SELECT RAISE(ABORT,'invalid_loss_responsibility'); END""")

def downgrade():
    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM owner_transfer_regularizations')).scalar():
        raise RuntimeError('Regularization history exists: destructive downgrade refused')
    for name in ('regularization_no_update','regularization_no_delete','loss_recognition_limit','loss_responsibility_parent'):
        op.execute('DROP TRIGGER '+name)
    op.drop_table('owner_transfer_regularizations')
