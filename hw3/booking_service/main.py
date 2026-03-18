"""Main FastAPI application for Booking Service."""
import logging
import sys
import uuid
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import grpc

from .config import settings
from .database import init_db, get_db
from .models import Booking, BookingStatus
from .schemas import (
    FlightResponse, CreateBookingRequest, BookingResponse,
    CancelBookingResponse, ErrorResponse
)
from .grpc_client import flight_client
from .circuit_breaker import CircuitBreakerError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Booking Service API",
    description="Flight booking management service",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info("Starting Booking Service...")
    init_db()
    logger.info("Booking Service started successfully")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.service_name}


@app.get("/flights", response_model=List[FlightResponse])
async def search_flights(
    origin: str = Query(..., description="Origin airport IATA code"),
    destination: str = Query(..., description="Destination airport IATA code"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    """
    Search for flights by route and optional date.
    Proxies request to Flight Service.
    """
    try:
        flights = flight_client.search_flights(origin, destination, date)

        # Convert protobuf to response model
        result = []
        for flight in flights:
            result.append(FlightResponse(
                id=flight.id,
                flight_number=flight.flight_number,
                airline=flight.airline,
                origin=flight.origin,
                destination=flight.destination,
                departure_time=flight.departure_time.ToDatetime(),
                arrival_time=flight.arrival_time.ToDatetime(),
                total_seats=flight.total_seats,
                available_seats=flight.available_seats,
                price=flight.price,
                status=flight_service_pb2.FlightStatus.Name(flight.status)
            ))

        return result

    except CircuitBreakerError as e:
        logger.error(f"Circuit breaker open: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            raise HTTPException(status_code=400, detail=e.details())
        raise HTTPException(status_code=500, detail="Flight service unavailable")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/flights/{flight_id}", response_model=FlightResponse)
async def get_flight(flight_id: int):
    """
    Get flight information by ID.
    Proxies request to Flight Service.
    """
    try:
        flight = flight_client.get_flight(flight_id)

        return FlightResponse(
            id=flight.id,
            flight_number=flight.flight_number,
            airline=flight.airline,
            origin=flight.origin,
            destination=flight.destination,
            departure_time=flight.departure_time.ToDatetime(),
            arrival_time=flight.arrival_time.ToDatetime(),
            total_seats=flight.total_seats,
            available_seats=flight.available_seats,
            price=flight.price,
            status=flight_service_pb2.FlightStatus.Name(flight.status)
        )

    except CircuitBreakerError as e:
        logger.error(f"Circuit breaker open: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=f"Flight {flight_id} not found")
        raise HTTPException(status_code=500, detail="Flight service unavailable")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/bookings", response_model=BookingResponse, status_code=201)
async def create_booking(
    request: CreateBookingRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new booking.

    Flow:
    1. Get flight information from Flight Service
    2. Reserve seats via Flight Service
    3. Calculate total price
    4. Create booking in database
    """
    booking_id = str(uuid.uuid4())

    try:
        # Step 1: Get flight information
        logger.info(f"Creating booking {booking_id}: Getting flight {request.flight_id}")
        flight = flight_client.get_flight(request.flight_id)

        # Step 2: Reserve seats (idempotent operation)
        logger.info(f"Creating booking {booking_id}: Reserving {request.seat_count} seats")
        reservation_response = flight_client.reserve_seats(
            flight_id=request.flight_id,
            seat_count=request.seat_count,
            booking_id=booking_id
        )

        if not reservation_response.success:
            raise HTTPException(status_code=400, detail=reservation_response.message)

        # Step 3: Calculate total price (snapshot at booking time)
        total_price = request.seat_count * flight.price

        # Step 4: Create booking
        booking = Booking(
            booking_id=booking_id,
            user_id=request.user_id,
            flight_id=request.flight_id,
            passenger_name=request.passenger_name,
            passenger_email=request.passenger_email,
            seat_count=request.seat_count,
            total_price=total_price,
            status=BookingStatus.CONFIRMED
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)

        logger.info(f"Booking created successfully: {booking_id}")
        return booking

    except CircuitBreakerError as e:
        logger.error(f"Circuit breaker open: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except grpc.RpcError as e:
        logger.error(f"gRPC error during booking creation: {e.code()} - {e.details()}")
        db.rollback()

        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(status_code=404, detail=f"Flight {request.flight_id} not found")
        elif e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
            raise HTTPException(status_code=409, detail=e.details())

        raise HTTPException(status_code=500, detail="Failed to create booking")
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error during booking creation: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: int, db: Session = Depends(get_db)):
    """Get booking by ID."""
    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")

    return booking


@app.get("/bookings", response_model=List[BookingResponse])
async def list_bookings(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    db: Session = Depends(get_db)
):
    """List bookings, optionally filtered by user ID."""
    query = db.query(Booking)

    if user_id is not None:
        query = query.filter(Booking.user_id == user_id)

    bookings = query.order_by(Booking.created_at.desc()).all()
    return bookings


@app.post("/bookings/{booking_id}/cancel", response_model=CancelBookingResponse)
async def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    """
    Cancel a booking.

    Flow:
    1. Check booking exists and is CONFIRMED
    2. Release reservation via Flight Service
    3. Update booking status to CANCELLED
    """
    booking = db.query(Booking).filter(Booking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")

    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel booking with status {booking.status.value}"
        )

    try:
        # Release reservation
        logger.info(f"Cancelling booking {booking.booking_id}: Releasing reservation")
        release_response = flight_client.release_reservation(booking.booking_id)

        if not release_response.success:
            logger.warning(f"Failed to release reservation: {release_response.message}")

        # Update booking status
        booking.status = BookingStatus.CANCELLED
        db.commit()
        db.refresh(booking)

        logger.info(f"Booking cancelled successfully: {booking.booking_id}")
        return CancelBookingResponse(
            success=True,
            message="Booking cancelled successfully",
            booking=booking
        )

    except CircuitBreakerError as e:
        logger.error(f"Circuit breaker open: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except grpc.RpcError as e:
        logger.error(f"gRPC error during cancellation: {e.code()} - {e.details()}")
        # Still cancel the booking even if release fails
        booking.status = BookingStatus.CANCELLED
        db.commit()
        db.refresh(booking)

        return CancelBookingResponse(
            success=True,
            message=f"Booking cancelled (warning: {e.details()})",
            booking=booking
        )
    except Exception as e:
        logger.error(f"Unexpected error during cancellation: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


# Import after app creation to avoid circular imports
import flight_service_pb2
