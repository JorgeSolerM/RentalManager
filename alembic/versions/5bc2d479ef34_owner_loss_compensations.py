"""Add immutable documented owner loss compensation, without banking entries."""
from alembic import op
import sqlalchemy as sa
revision='5bc2d479ef34'
down_revision='4ab1c368de23'
branch_labels=None
depends_on=None
DDL = [
    """CREATE TABLE owner_loss_compensation_authorizations (
	id INTEGER NOT NULL, 
	incident_id INTEGER NOT NULL, 
	loss_id INTEGER NOT NULL, 
	responsibility_id INTEGER NOT NULL, 
	owner_id INTEGER NOT NULL, 
	agreement_reference VARCHAR(160) NOT NULL, 
	agreement_key VARCHAR(64) NOT NULL, 
	settlement_ids JSON NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	reason TEXT NOT NULL, 
	evidence TEXT NOT NULL, 
	operator_id VARCHAR(160), 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	before_state JSON NOT NULL, 
	after_state JSON NOT NULL, 
	request_key VARCHAR(36) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	reviewed_state VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (amount > 0), 
	CHECK (length(trim(reason))>0 AND length(trim(evidence))>0 AND length(trim(agreement_reference))>0), 
	FOREIGN KEY(incident_id) REFERENCES owner_transfer_incidents (id) ON DELETE RESTRICT, 
	UNIQUE (loss_id), 
	FOREIGN KEY(loss_id) REFERENCES owner_transfer_regularizations (id) ON DELETE RESTRICT, 
	UNIQUE (responsibility_id), 
	FOREIGN KEY(responsibility_id) REFERENCES owner_transfer_regularizations (id) ON DELETE RESTRICT, 
	FOREIGN KEY(owner_id) REFERENCES owners (id) ON DELETE RESTRICT, 
	UNIQUE (agreement_key), 
	UNIQUE (request_key)
)""",
    """CREATE INDEX ix_owner_loss_compensation_authorizations_incident_id ON owner_loss_compensation_authorizations (incident_id)""",
    """CREATE INDEX ix_owner_loss_compensation_authorizations_owner_id ON owner_loss_compensation_authorizations (owner_id)""",
    """CREATE TABLE owner_loss_compensation_applications (
	id INTEGER NOT NULL, 
	authorization_id INTEGER NOT NULL, 
	settlement_id INTEGER NOT NULL, 
	owner_id INTEGER NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	reason TEXT NOT NULL, 
	evidence TEXT NOT NULL, 
	operator_id VARCHAR(160), 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	before_state JSON NOT NULL, 
	after_state JSON NOT NULL, 
	request_key VARCHAR(36) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	reviewed_state VARCHAR(64) NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (amount > 0), 
	CHECK (length(trim(reason))>0 AND length(trim(evidence))>0), 
	FOREIGN KEY(authorization_id) REFERENCES owner_loss_compensation_authorizations (id) ON DELETE RESTRICT, 
	FOREIGN KEY(settlement_id) REFERENCES owner_settlements (id) ON DELETE RESTRICT, 
	FOREIGN KEY(owner_id) REFERENCES owners (id) ON DELETE RESTRICT, 
	UNIQUE (request_key)
)""",
    """CREATE INDEX ix_owner_loss_compensation_applications_authorization_id ON owner_loss_compensation_applications (authorization_id)""",
    """CREATE INDEX ix_owner_loss_compensation_applications_owner_id ON owner_loss_compensation_applications (owner_id)""",
    """CREATE INDEX ix_owner_loss_compensation_applications_settlement_id ON owner_loss_compensation_applications (settlement_id)""",
]

TRIGGERS = {
 'loss_comp_authorization_parent': """CREATE TRIGGER loss_comp_authorization_parent BEFORE INSERT ON owner_loss_compensation_authorizations WHEN NOT EXISTS (
 SELECT 1 FROM owner_transfer_regularizations l JOIN owner_transfer_regularizations r ON r.id=NEW.responsibility_id
 WHERE l.id=NEW.loss_id AND l.kind='recognize' AND l.incident_id=NEW.incident_id
 AND r.incident_id=l.incident_id AND (r.id=l.id OR r.loss_id=l.id)
 AND r.responsible='owner' AND r.responsible_owner_id=NEW.owner_id AND NEW.amount<=r.amount
 ) BEGIN SELECT RAISE(ABORT,'invalid_compensation_responsibility'); END""",
 'loss_comp_application_limit': """CREATE TRIGGER loss_comp_application_limit BEFORE INSERT ON owner_loss_compensation_applications WHEN NOT EXISTS (
 SELECT 1 FROM owner_loss_compensation_authorizations a JOIN owner_settlements s ON s.id=NEW.settlement_id
 WHERE a.id=NEW.authorization_id AND a.owner_id=NEW.owner_id AND s.owner_id=NEW.owner_id AND s.status='closed'
 AND EXISTS(SELECT 1 FROM json_each(a.settlement_ids) j WHERE j.value=NEW.settlement_id)
 AND ROUND(NEW.amount+COALESCE((SELECT SUM(p.amount) FROM owner_loss_compensation_applications p WHERE p.authorization_id=a.id),0),2)<=a.amount
 AND ROUND(NEW.amount+COALESCE((SELECT SUM(p.amount) FROM owner_loss_compensation_applications p WHERE p.settlement_id=s.id),0),2)<=CAST(json_extract(s.snapshot,'$.totals.payout_due') AS NUMERIC)
 ) BEGIN SELECT RAISE(ABORT,'invalid_compensation_application'); END""",
}
for table,prefix in [('owner_loss_compensation_authorizations','loss_comp_authorization'),('owner_loss_compensation_applications','loss_comp_application')]:
 for action in ('UPDATE','DELETE'):
  name=prefix+'_no_'+action.lower()
  TRIGGERS[name]=f"CREATE TRIGGER {name} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_loss_compensation'); END"

def upgrade():
 for sql in DDL:op.execute(sql)
 for sql in TRIGGERS.values():op.execute(sql)

def downgrade():
 for table in ('owner_loss_compensation_applications','owner_loss_compensation_authorizations'):
  if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM '+table)).scalar():raise RuntimeError('Compensation history exists: destructive downgrade refused')
 for name in TRIGGERS:op.execute('DROP TRIGGER '+name)
 op.drop_table('owner_loss_compensation_applications')
 op.drop_table('owner_loss_compensation_authorizations')
