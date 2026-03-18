"""Flight Service gRPC implementation."""
import logging
from datetime import datetime
from typing import Optional
import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import and_
from sqlalchemy.orm import Session

from .database import get_db
from .models import Flight, SeatReservation, FlightStatus, ReservationStatus
from .cache import cache
import flight_service_pb2
import flight_service_pb2_grpc

logger = logging.getLogger(__name__)


class FlightServiceServicer(flight_service_pb2_grpc.FlightServiceServicer):
    """Implementation of FlightService gRPC service."""

    def _flight_to_proto(self, flight: Flight) -> flight_service_pb2.Flight:
        """Convert Flight model to protobuf message."""
        departure_ts = Timestamp()
        departure_ts.FromDatetime(flight.departure_time)

        arrival_ts = Timestamp()
        arrival_ts.FromDatetime(flight.arrival_time)

        # Map status
        status_map = {
            FlightStatus.SCHEDULED: flight_service_pb2.SCHEDULED,
            FlightStatus.DEPARTED: flight_service_pb2.DEPARTED,
            FlightStatus.CANCELLED: flight_service_pb2.CANCELLED,
            FlightStatus.COMPLETED: flight_service_pb2.COMPLETED,
        }

        return flight_service_pb2.Flight(
            id=flight.id,
            flight_number=flight.flight_number,
            airline=flight.airline,
            origin=flight.origin,
            destination=flight.destination,
            departure_time=departure_ts,
            arrival_time=arrival_ts,
            total_seats=flight.total_seats,
            available_seats=flight.available_seats,
            price=flight.price,
            status=status_map.get(flight.status, flight_service_pb2.FLIGHT_STATUS_UNSPECIFIED)
        )

    def _flight_to_dict(self, flight: Flight) -> dict:
        """Convert Flight model to dictionary for caching."""
        return {
            'id': flight.id,
            'flight_number': flight.flight_number,
            'airline': flight.airline,
            'origin': flight.origin,
            'destination': flight.destination,
            'departure_time': flight.departure_time.isoformat(),
            'arrival_time': flight.arrival_time.isoformat(),
            'total_seats': flight.total_seats,
            'available_seats': flight.available_seats,
            'price': flight.price,
            'status': flight.status.value
        }

    def _dict_to_proto(self, data: dict) -> flight_service_pb2.Flight:
        """Convert dictionary to protobuf message."""
        departure_ts = Timestamp()
        departure_ts.FromDatetime(datetime.fromisoformat(data['departure_time']))

        arrival_ts = Timestamp()
        arrival_ts.FromDatetime(datetime.fromisoformat(data['arrival_time']))

        status_map = {
            'SCHEDULED': flight_service_pb2.SCHEDULED,
            'DEPARTED': flight_service_pb2.DEPARTED,
            'CANCELLED': flight_service_pb2.CANCELLED,
            'COMPLETED': flight_service_pb2.COMPLETED,
        }

        return flight_service_pb2.Flight(
            id=data['id'],
            flight_number=data['flight_number'],
            airline=data['airline'],
            origin=data['origin'],
            destination=data['destination'],
            departure_time=departure_ts,
            arrival_time=arrival_ts,
            total_seats=data['total_seats'],
            available_seats=data['available_seats'],
            price=data['price'],
            status=status_map.get(data['status'], flight_service_pb2.FLIGHT_STATUS_UNSPECIFIED)
        )

    def SearchFlights(
        self,
        request: flight_service_pb2.SearchFlightsRequest,
        context: grpc.ServicerContext
    ) -> flight_service_pb2.SearchFlightsResponse:
        """Search for flights by route and optional date."""
        logger.info(f"SearchFlights: {request.origin} -> {request.destination}, date: {request.date}")

        # Check cache
        cache_key = f"search:{request.origin}:{request.destination}:{request.date or 'any'}"
        cached = cache.get(cache_key)
        if cached:
            flights = [self._dict_to_proto(f) for f in cached]
            return flight_service_pb2.SearchFlightsResponse(flights=flights)

        try:
            with get_db() as db:
                query = db.query(Flight).filter(
                    and_(
                        Flight.origin == request.origin,
                        Flight.destination == request.destination,
                        Flight.status == FlightStatus.SCHEDULED
                    )
                )

                # Filter by date if provided
                if request.date:
                    try:
                        date_obj = datetime.strptime(request.date, '%Y-%m-%d').date()
                        query = query.filter(
                            db.func.date(Flight.departure_time) == date_obj
                        )
                    except ValueError:
                        context.abort(
                            grpc.StatusCode.INVALID_ARGUMENT,
                            f"Invalid date format: {request.date}. Expected YYYY-MM-DD"
                        )

                flights = query.all()

                # Cache results
                flights_data = [self._flight_to_dict(f) for f in flights]
                cache.set(cache_key, flights_data)

                # Convert to proto
                proto_flights = [self._flight_to_proto(f) for f in flights]

                logger.info(f"Found {len(proto_flights)} flights")
                return flight_service_pb2.SearchFlightsResponse(flights=proto_flights)

        except Exception as e:
            logger.error(f"SearchFlights error: {e}")
            context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    def GetFlight(
        self,
        request: flight_service_pb2.GetFlightRequest,
        context: grpc.ServicerContext
    ) -> flight_service_pb2.Flight:
        """Get flight information by ID."""
        logger.info(f"GetFlight: {request.flight_id}")

        # Check cache
        cache_key = f"flight:{request.flight_id}"
        cached = cache.get(cache_key)
        if cached:
            return self._dict_to_proto(cached)

        try:
            with get_db() as db:
                flight = db.query(Flight).filter(Flight.id == request.flight_id).first()

                if not flight:
                    logger.warning(f"Flight not found: {request.flight_id}")
                    context.abort(grpc.StatusCode.NOT_FOUND, f"Flight {request.flight_id} not found")

                # Cache result
                cache.set(cache_key, self._flight_to_dict(flight))

                return self._flight_to_proto(flight)

        except grpc.RpcError:
            raise
        except Exception as e:
            logger.error(f"GetFlight error: {e}")
            context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    def ReserveSeats(
        self,
        request: flight_service_pb2.ReserveSeatsRequest,
        context: grpc.ServicerContext
    ) -> flight_service_pb2.ReserveSeatsResponse:
        """Reserve seats for a booking (atomic operation with idempotency)."""
        logger.info(f"ReserveSeats: flight={request.flight_id}, seats={request.seat_count}, booking={request.booking_id}")

        try:
            with get_db() as db:
                # Check for existing reservation (idempotency)
                existing = db.query(SeatReservation).filter(
                    SeatReservation.booking_id == request.booking_id
                ).first()

                if existing:
                    logger.info(f"Reservation already exists for booking {request.booking_id}")
                    return flight_service_pb2.ReserveSeatsResponse(
                        reservation_id=existing.id,
                        success=True,
                        message="Reservation already exists (idempotent)"
                    )

                # Lock the flight row for update (prevent race conditions)
                flight = db.query(Flight).filter(Flight.id == request.flight_id).with_for_update().first()

                if not flight:
                    context.abort(grpc.StatusCode.NOT_FOUND, f"Flight {request.flight_id} not found")

                # Check seat availability
                if flight.available_seats < request.seat_count:
                    logger.warning(f"Not enough seats: requested={request.seat_count}, available={flight.available_seats}")
                    context.abort(
                        grpc.StatusCode.RESOURCE_EXHAUSTED,
                        f"Not enough seats available. Requested: {request.seat_count}, Available: {flight.available_seats}"
                    )

                # Update available seats
                flight.available_seats -= request.seat_count

                # Create reservation
                reservation = SeatReservation(
                    flight_id=request.flight_id,
                    booking_id=request.booking_id,
                    seat_count=request.seat_count,
                    status=ReservationStatus.ACTIVE
                )
                db.add(reservation)
                db.flush()  # Get reservation ID

                # Invalidate cache
                cache.invalidate_flight(request.flight_id)

                logger.info(f"Reservation created: id={reservation.id}")
                return flight_service_pb2.ReserveSeatsResponse(
                    reservation_id=reservation.id,
                    success=True,
                    message="Seats reserved successfully"
                )

        except grpc.RpcError:
            raise
        except Exception as e:
            logger.error(f"ReserveSeats error: {e}")
            context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    def ReleaseReservation(
        self,
        request: flight_service_pb2.ReleaseReservationRequest,
        context: grpc.ServicerContext
    ) -> flight_service_pb2.ReleaseReservationResponse:
        """Release a reservation and return seats."""
        logger.info(f"ReleaseReservation: booking={request.booking_id}")

        try:
            with get_db() as db:
                # Find active reservation
                reservation = db.query(SeatReservation).filter(
                    and_(
                        SeatReservation.booking_id == request.booking_id,
                        SeatReservation.status == ReservationStatus.ACTIVE
                    )
                ).first()

                if not reservation:
                    logger.warning(f"Active reservation not found for booking {request.booking_id}")
                    return flight_service_pb2.ReleaseReservationResponse(
                        success=False,
                        message=f"Active reservation not found for booking {request.booking_id}"
                    )

                # Lock the flight row for update
                flight = db.query(Flight).filter(
                    Flight.id == reservation.flight_id
                ).with_for_update().first()

                if not flight:
                    context.abort(grpc.StatusCode.NOT_FOUND, f"Flight {reservation.flight_id} not found")

                # Return seats
                flight.available_seats += reservation.seat_count

                # Update reservation status
                reservation.status = ReservationStatus.RELEASED

                # Invalidate cache
                cache.invalidate_flight(reservation.flight_id)

                logger.info(f"Reservation released: {reservation.id}, returned {reservation.seat_count} seats")
                return flight_service_pb2.ReleaseReservationResponse(
                    success=True,
                    message=f"Released {reservation.seat_count} seats"
                )

        except grpc.RpcError:
            raise
        except Exception as e:
            logger.error(f"ReleaseReservation error: {e}")
            context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")
