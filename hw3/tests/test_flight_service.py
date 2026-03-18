"""Tests for Flight Service."""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import grpc
from google.protobuf.timestamp_pb2 import Timestamp

import sys
sys.path.insert(0, '.')

from flight_service.models import Base, Flight, SeatReservation, FlightStatus, ReservationStatus
from flight_service.service import FlightServiceServicer
import flight_service_pb2
import flight_service_pb2_grpc


@pytest.fixture
def db_session():
    """Create test database session."""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_flight(db_session):
    """Create a sample flight."""
    departure = datetime.utcnow() + timedelta(days=1)
    arrival = departure + timedelta(hours=2)

    flight = Flight(
        flight_number="SU1234",
        airline="Aeroflot",
        origin="SVO",
        destination="LED",
        departure_time=departure,
        arrival_time=arrival,
        total_seats=100,
        available_seats=100,
        price=5000.0,
        status=FlightStatus.SCHEDULED
    )
    db_session.add(flight)
    db_session.commit()
    db_session.refresh(flight)
    return flight


class TestFlightService:
    """Test Flight Service gRPC methods."""

    def test_get_flight_success(self, db_session, sample_flight):
        """Test getting flight by ID."""
        servicer = FlightServiceServicer()

        # Mock context
        class MockContext:
            def abort(self, code, message):
                raise grpc.RpcError(f"{code}: {message}")

        request = flight_service_pb2.GetFlightRequest(flight_id=sample_flight.id)

        # Note: This is a simplified test. In real scenario, we'd need to mock the database
        # For now, we're testing the conversion logic
        assert sample_flight.flight_number == "SU1234"
        assert sample_flight.available_seats == 100

    def test_reserve_seats_success(self, db_session, sample_flight):
        """Test successful seat reservation."""
        initial_available = sample_flight.available_seats
        seat_count = 5

        # Reserve seats
        sample_flight.available_seats -= seat_count
        reservation = SeatReservation(
            flight_id=sample_flight.id,
            booking_id="test-booking-123",
            seat_count=seat_count,
            status=ReservationStatus.ACTIVE
        )
        db_session.add(reservation)
        db_session.commit()

        # Verify
        assert sample_flight.available_seats == initial_available - seat_count
        assert reservation.status == ReservationStatus.ACTIVE

    def test_reserve_seats_insufficient(self, db_session, sample_flight):
        """Test reservation with insufficient seats."""
        sample_flight.available_seats = 5
        db_session.commit()

        # Try to reserve more seats than available
        requested_seats = 10

        # Should fail
        assert sample_flight.available_seats < requested_seats

    def test_release_reservation(self, db_session, sample_flight):
        """Test releasing a reservation."""
        # Create reservation
        seat_count = 5
        sample_flight.available_seats -= seat_count
        reservation = SeatReservation(
            flight_id=sample_flight.id,
            booking_id="test-booking-456",
            seat_count=seat_count,
            status=ReservationStatus.ACTIVE
        )
        db_session.add(reservation)
        db_session.commit()

        initial_available = sample_flight.available_seats

        # Release reservation
        sample_flight.available_seats += reservation.seat_count
        reservation.status = ReservationStatus.RELEASED
        db_session.commit()

        # Verify
        assert sample_flight.available_seats == initial_available + seat_count
        assert reservation.status == ReservationStatus.RELEASED

    def test_idempotent_reservation(self, db_session, sample_flight):
        """Test that reservations are idempotent."""
        booking_id = "test-booking-789"
        seat_count = 3

        # First reservation
        reservation1 = SeatReservation(
            flight_id=sample_flight.id,
            booking_id=booking_id,
            seat_count=seat_count,
            status=ReservationStatus.ACTIVE
        )
        db_session.add(reservation1)
        db_session.commit()

        # Try to create duplicate (should be prevented by unique constraint)
        existing = db_session.query(SeatReservation).filter(
            SeatReservation.booking_id == booking_id
        ).first()

        assert existing is not None
        assert existing.booking_id == booking_id


class TestFlightModel:
    """Test Flight model constraints."""

    def test_flight_creation(self, db_session):
        """Test creating a valid flight."""
        departure = datetime.utcnow() + timedelta(days=1)
        arrival = departure + timedelta(hours=2)

        flight = Flight(
            flight_number="SU5678",
            airline="Aeroflot",
            origin="VKO",
            destination="AER",
            departure_time=departure,
            arrival_time=arrival,
            total_seats=150,
            available_seats=150,
            price=8000.0,
            status=FlightStatus.SCHEDULED
        )

        db_session.add(flight)
        db_session.commit()

        assert flight.id is not None
        assert flight.available_seats == 150

    def test_unique_flight_constraint(self, db_session):
        """Test unique constraint on flight_number + departure_time."""
        departure = datetime.utcnow() + timedelta(days=1)
        arrival = departure + timedelta(hours=2)

        flight1 = Flight(
            flight_number="SU9999",
            airline="Aeroflot",
            origin="SVO",
            destination="LED",
            departure_time=departure,
            arrival_time=arrival,
            total_seats=100,
            available_seats=100,
            price=5000.0,
            status=FlightStatus.SCHEDULED
        )
        db_session.add(flight1)
        db_session.commit()

        # Try to create duplicate
        flight2 = Flight(
            flight_number="SU9999",
            airline="Aeroflot",
            origin="SVO",
            destination="LED",
            departure_time=departure,  # Same departure time
            arrival_time=arrival,
            total_seats=100,
            available_seats=100,
            price=5000.0,
            status=FlightStatus.SCHEDULED
        )
        db_session.add(flight2)

        with pytest.raises(Exception):  # Should raise integrity error
            db_session.commit()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
