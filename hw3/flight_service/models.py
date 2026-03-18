"""Database models for Flight Service."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    Enum, ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum


Base = declarative_base()


class FlightStatus(str, enum.Enum):
    """Flight status enum."""
    SCHEDULED = "SCHEDULED"
    DEPARTED = "DEPARTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class ReservationStatus(str, enum.Enum):
    """Reservation status enum."""
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


class Flight(Base):
    """Flight model."""
    __tablename__ = "flights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flight_number = Column(String(10), nullable=False)
    airline = Column(String(100), nullable=False)
    origin = Column(String(3), nullable=False)  # IATA code
    destination = Column(String(3), nullable=False)  # IATA code
    departure_time = Column(DateTime, nullable=False)
    arrival_time = Column(DateTime, nullable=False)
    total_seats = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(Enum(FlightStatus), nullable=False, default=FlightStatus.SCHEDULED)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    reservations = relationship("SeatReservation", back_populates="flight")

    # Constraints
    __table_args__ = (
        CheckConstraint('total_seats > 0', name='check_total_seats_positive'),
        CheckConstraint('available_seats >= 0', name='check_available_seats_non_negative'),
        CheckConstraint('available_seats <= total_seats', name='check_available_seats_lte_total'),
        CheckConstraint('price > 0', name='check_price_positive'),
        UniqueConstraint('flight_number', 'departure_time', name='uq_flight_number_departure'),
    )


class SeatReservation(Base):
    """Seat reservation model."""
    __tablename__ = "seat_reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flight_id = Column(Integer, ForeignKey('flights.id', ondelete='CASCADE'), nullable=False)
    booking_id = Column(String(100), nullable=False, unique=True)  # From Booking Service
    seat_count = Column(Integer, nullable=False)
    status = Column(Enum(ReservationStatus), nullable=False, default=ReservationStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    flight = relationship("Flight", back_populates="reservations")

    # Constraints
    __table_args__ = (
        CheckConstraint('seat_count > 0', name='check_seat_count_positive'),
    )
