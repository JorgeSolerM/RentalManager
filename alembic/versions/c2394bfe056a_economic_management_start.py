"""Independent accounting-start branch; no fiscal migration dependency."""
from alembic import op
import sqlalchemy as sa

revision = 'c2394bfe056a'
down_revision = 'b1283aedf459'
branch_labels = ('economic_start',)
depends_on = None


def upgrade():
    op.add_column('bookings', sa.Column('economic_management_start', sa.Date(), nullable=True))
    op.add_column('bookings', sa.Column('economic_management_start_configured_at', sa.DateTime(), nullable=True))
    for event in ('INSERT', 'UPDATE'):
        op.execute(f"""CREATE TRIGGER economic_start_first_day_{event.lower()}
        BEFORE {event} ON bookings WHEN NEW.economic_management_start IS NOT NULL
        AND (strftime('%d', NEW.economic_management_start) IS NULL OR strftime('%d', NEW.economic_management_start) != '01')
        BEGIN SELECT RAISE(ABORT, 'economic_start_requires_first_day'); END""")


def downgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM bookings WHERE economic_management_start IS NOT NULL OR economic_management_start_configured_at IS NOT NULL')).scalar():
        raise RuntimeError('No se elimina una configuración de inicio contable existente.')
    op.execute('DROP TRIGGER economic_start_first_day_insert')
    op.execute('DROP TRIGGER economic_start_first_day_update')
    op.drop_column('bookings', 'economic_management_start_configured_at')
    op.drop_column('bookings', 'economic_management_start')
