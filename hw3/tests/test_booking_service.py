"""Tests for Booking Service."""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, '.')

from booking_service.models import Base, Booking, BookingStatus
from booking_service.main import app


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
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_booking(db_session):
    """Create a sample booking."""
    booking = Booking(
        booking_id="test-booking-123",
        user_id=1,
        flight_id=100,
        passenger_name="John Doe",
        passenger_email="john@example.com",
        seat_count=2,
        total_price=10000.0,
        status=BookingStatus.CONFIRMED
    )
    db_session.add(booking)
    db_session.commit()
    db_session.refresh(booking)
    return booking


class TestBookingModel:
    """Test Booking model."""

    def test_booking_creation(self, db_session):
        """Test creating a valid booking."""
        booking = Booking(
            booking_id="test-booking-456",
            user_id=2,
            flight_id=101,
            passenger_name="Jane Smith",
            passenger_email="jane@example.com",
            seat_count=1,
            total_price=5000.0,
            status=BookingStatus.CONFIRMED
        )

        db_session.add(booking)
        db_session.commit()

        assert booking.id is not None
        assert booking.status == BookingStatus.CONFIRMED

    def test_booking_cancellation(self, db_session, sample_booking):
        """Test cancelling a booking."""
        assert sample_booking.status == BookingStatus.CONFIRMED

        sample_booking.status = BookingStatus.CANCELLED
        db_session.commit()

        assert sample_booking.status == BookingStatus.CANCELLED

    def test_unique_booking_id(self, db_session, sample_booking):
        """Test unique constraint on booking_id."""
        duplicate = Booking(
            booking_id=sample_booking.booking_id,  # Same booking_id
            user_id=3,
            flight_id=102,
            passenger_name="Test User",
            passenger_email="test@example.com",
            seat_count=1,
            total_price=5000.0,
            status=BookingStatus.CONFIRMED
        )

        db_session.add(duplicate)

        with pytest.raises(Exception):  # Should raise integrity error
            db_session.commit()


class TestBookingAPI:
    """Test Booking Service REST API."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_get_booking_not_found(self, client):
        """Test getting non-existent booking."""
        response = client.get("/bookings/99999")
        assert response.status_code == 404


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_circuit_breaker_states(self):
        """Test circuit breaker state transitions."""
        from booking_service.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

        # Initial state should be CLOSED
        assert cb.get_state() == CircuitState.CLOSED

        # Simulate failures
        def failing_func():
            raise Exception("Test failure")

        for i in range(3):
            try:
                cb.call(failing_func)
            except Exception:
                pass

        # Should transition to OPEN after threshold
        assert cb.get_state() == CircuitState.OPEN

    def test_circuit_breaker_success_resets_count(self):
        """Test that successful calls reset failure count."""
        from booking_service.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(failure_threshold=5)

        # Fail a few times
        def failing_func():
            raise Exception("Test failure")

        for i in range(2):
            try:
                cb.call(failing_func)
            except Exception:
                pass

        # Should still be CLOSED
        assert cb.get_state() == CircuitState.CLOSED

        # Successful call should reset count
        def success_func():
            return "success"

        result = cb.call(success_func)
        assert result == "success"
        assert cb.failure_count == 0


class TestRetryLogic:
    """Test retry logic."""

    def test_retry_calculation(self):
        """Test exponential backoff calculation."""
        from booking_service.grpc_client import FlightServiceClient

        client = FlightServiceClient()

        # Test backoff calculation
        backoff_0 = client._calculate_backoff(0)
        backoff_1 = client._calculate_backoff(1)
        backoff_2 = client._calculate_backoff(2)

        assert backoff_1 > backoff_0
        assert backoff_2 > backoff_1
        assert backoff_2 <= client.max_backoff_ms / 1000.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
