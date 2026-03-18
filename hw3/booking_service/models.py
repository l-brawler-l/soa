"""Database models for Booking Service."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
import enum


Base = declarative_base()


class BookingStatus(str, enum.Enum):
    """Booking status enum."""
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class Booking(Base):
    """Booking model."""
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(String(100), unique=True, nullable=False)  # UUID for idempotency
    user_id = Column(Integer, nullable=False)
    flight_id = Column(Integer, nullable=False)  # Reference to Flight Service
    passenger_name = Column(String(200), nullable=False)
    passenger_email = Column(String(200), nullable=False)
    seat_count = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)  # Snapshot at booking time
    status = Column(Enum(BookingStatus), nullable=False, default=BookingStatus.CONFIRMED)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Constraints
    __table_args__ = (
        CheckConstraint('seat_count > 0', name='check_seat_count_positive'),
        CheckConstraint('total_price > 0', name='check_total_price_positive'),
    )
