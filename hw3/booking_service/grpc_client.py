"""gRPC client for Flight Service with retry logic."""
import logging
import time
import grpc
from typing import Optional, List

from .config import settings
from .circuit_breaker import with_circuit_breaker, CircuitBreakerError
import flight_service_pb2
import flight_service_pb2_grpc

logger = logging.getLogger(__name__)


class FlightServiceClient:
    """Client for Flight Service gRPC API with retry and circuit breaker."""

    def __init__(self):
        """Initialize gRPC client."""
        self.address = settings.flight_service_address
        self.api_key = settings.flight_service_api_key
        self.max_attempts = settings.retry_max_attempts
        self.initial_backoff_ms = settings.retry_initial_backoff_ms
        self.max_backoff_ms = settings.retry_max_backoff_ms

    def _get_metadata(self) -> List[tuple]:
        """Get gRPC metadata with API key."""
        return [('x-api-key', self.api_key)]

    def _should_retry(self, error: grpc.RpcError) -> bool:
        """
        Determine if error is retryable.

        Retry only for:
        - UNAVAILABLE
        - DEADLINE_EXCEEDED

        Do NOT retry for:
        - INVALID_ARGUMENT
        - NOT_FOUND
        - RESOURCE_EXHAUSTED
        - UNAUTHENTICATED
        """
        if not isinstance(error, grpc.RpcError):
            return False

        code = error.code()
        retryable_codes = [
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED
        ]

        return code in retryable_codes

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff in seconds."""
        backoff_ms = min(
            self.initial_backoff_ms * (2 ** attempt),
            self.max_backoff_ms
        )
        return backoff_ms / 1000.0

    def _call_with_retry(self, func, *args, **kwargs):
        """
        Execute gRPC call with retry logic.

        Args:
            func: gRPC method to call
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Response from gRPC call

        Raises:
            grpc.RpcError: If all retries fail
        """
        last_error = None

        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)
            except grpc.RpcError as e:
                last_error = e

                if not self._should_retry(e):
                    logger.warning(f"Non-retryable error: {e.code()} - {e.details()}")
                    raise

                if attempt < self.max_attempts - 1:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.max_attempts} failed: {e.code()}. "
                        f"Retrying in {backoff:.3f}s..."
                    )
                    time.sleep(backoff)
                else:
                    logger.error(f"All {self.max_attempts} attempts failed")

        raise last_error

    @with_circuit_breaker
    def search_flights(
        self,
        origin: str,
        destination: str,
        date: Optional[str] = None
    ) -> List[flight_service_pb2.Flight]:
        """
        Search for flights.

        Args:
            origin: Origin airport IATA code
            destination: Destination airport IATA code
            date: Optional date in YYYY-MM-DD format

        Returns:
            List of flights
        """
        logger.info(f"Searching flights: {origin} -> {destination}, date: {date}")

        def _call():
            with grpc.insecure_channel(self.address) as channel:
                stub = flight_service_pb2_grpc.FlightServiceStub(channel)
                request = flight_service_pb2.SearchFlightsRequest(
                    origin=origin,
                    destination=destination,
                    date=date or ""
                )
                response = stub.SearchFlights(request, metadata=self._get_metadata())
                return list(response.flights)

        return self._call_with_retry(_call)

    @with_circuit_breaker
    def get_flight(self, flight_id: int) -> flight_service_pb2.Flight:
        """
        Get flight by ID.

        Args:
            flight_id: Flight ID

        Returns:
            Flight information
        """
        logger.info(f"Getting flight: {flight_id}")

        def _call():
            with grpc.insecure_channel(self.address) as channel:
                stub = flight_service_pb2_grpc.FlightServiceStub(channel)
                request = flight_service_pb2.GetFlightRequest(flight_id=flight_id)
                return stub.GetFlight(request, metadata=self._get_metadata())

        return self._call_with_retry(_call)

    @with_circuit_breaker
    def reserve_seats(
        self,
        flight_id: int,
        seat_count: int,
        booking_id: str
    ) -> flight_service_pb2.ReserveSeatsResponse:
        """
        Reserve seats for a booking (idempotent).

        Args:
            flight_id: Flight ID
            seat_count: Number of seats to reserve
            booking_id: Booking ID for idempotency

        Returns:
            Reservation response
        """
        logger.info(f"Reserving {seat_count} seats on flight {flight_id} for booking {booking_id}")

        def _call():
            with grpc.insecure_channel(self.address) as channel:
                stub = flight_service_pb2_grpc.FlightServiceStub(channel)
                request = flight_service_pb2.ReserveSeatsRequest(
                    flight_id=flight_id,
                    seat_count=seat_count,
                    booking_id=booking_id
                )
                return stub.ReserveSeats(request, metadata=self._get_metadata())

        return self._call_with_retry(_call)

    @with_circuit_breaker
    def release_reservation(
        self,
        booking_id: str
    ) -> flight_service_pb2.ReleaseReservationResponse:
        """
        Release a reservation.

        Args:
            booking_id: Booking ID

        Returns:
            Release response
        """
        logger.info(f"Releasing reservation for booking {booking_id}")

        def _call():
            with grpc.insecure_channel(self.address) as channel:
                stub = flight_service_pb2_grpc.FlightServiceStub(channel)
                request = flight_service_pb2.ReleaseReservationRequest(
                    booking_id=booking_id
                )
                return stub.ReleaseReservation(request, metadata=self._get_metadata())

        return self._call_with_retry(_call)


# Global client instance
flight_client = FlightServiceClient()
