"""Initial schema for Booking Service

Revision ID: 001
Revises:
Create Date: 2026-03-18 19:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create bookings table."""
    op.create_table(
        'bookings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('booking_id', sa.String(length=100), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('flight_id', sa.Integer(), nullable=False),
        sa.Column('passenger_name', sa.String(length=200), nullable=False),
        sa.Column('passenger_email', sa.String(length=200), nullable=False),
        sa.Column('seat_count', sa.Integer(), nullable=False),
        sa.Column('total_price', sa.Float(), nullable=False),
        sa.Column('status', sa.Enum('CONFIRMED', 'CANCELLED', name='bookingstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint('seat_count > 0', name='check_seat_count_positive'),
        sa.CheckConstraint('total_price > 0', name='check_total_price_positive'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('booking_id')
    )


def downgrade() -> None:
    """Drop bookings table."""
    op.drop_table('bookings')
    op.execute('DROP TYPE IF EXISTS bookingstatus')
