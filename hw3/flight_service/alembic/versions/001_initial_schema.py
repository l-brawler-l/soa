"""Initial schema for Flight Service

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
    """Create flights and seat_reservations tables."""
    # Create flights table
    op.create_table(
        'flights',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('flight_number', sa.String(length=10), nullable=False),
        sa.Column('airline', sa.String(length=100), nullable=False),
        sa.Column('origin', sa.String(length=3), nullable=False),
        sa.Column('destination', sa.String(length=3), nullable=False),
        sa.Column('departure_time', sa.DateTime(), nullable=False),
        sa.Column('arrival_time', sa.DateTime(), nullable=False),
        sa.Column('total_seats', sa.Integer(), nullable=False),
        sa.Column('available_seats', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('status', sa.Enum('SCHEDULED', 'DEPARTED', 'CANCELLED', 'COMPLETED', name='flightstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint('total_seats > 0', name='check_total_seats_positive'),
        sa.CheckConstraint('available_seats >= 0', name='check_available_seats_non_negative'),
        sa.CheckConstraint('available_seats <= total_seats', name='check_available_seats_lte_total'),
        sa.CheckConstraint('price > 0', name='check_price_positive'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('flight_number', 'departure_time', name='uq_flight_number_departure')
    )

    # Create seat_reservations table
    op.create_table(
        'seat_reservations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('flight_id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.String(length=100), nullable=False),
        sa.Column('seat_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'RELEASED', 'EXPIRED', name='reservationstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint('seat_count > 0', name='check_seat_count_positive'),
        sa.ForeignKeyConstraint(['flight_id'], ['flights.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('booking_id')
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('seat_reservations')
    op.drop_table('flights')
    op.execute('DROP TYPE IF EXISTS reservationstatus')
    op.execute('DROP TYPE IF EXISTS flightstatus')
