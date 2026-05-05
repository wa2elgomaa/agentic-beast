##
# Auto-generated Alembic migration script template
#
from alembic import op
import sqlalchemy as sa
${imports if imports else ''}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision) if down_revision else 'None'}
branch_labels = ${repr(branch_labels) if branch_labels else 'None'}
depends_on = ${repr(depends_on) if depends_on else 'None'}


def upgrade():
    """Write your upgrade migrations here."""
    ${upgrades if upgrades else 'pass'}


def downgrade():
    """Write your downgrade migrations here."""
    ${downgrades if downgrades else 'pass'}
