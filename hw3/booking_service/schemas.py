"""Pydantic schemas for Booking Service API."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class FlightResponse(BaseModel):
    """Flight information response."""
    id: int
    flight_number: str
    airline: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    total_seats: int
    available_seats: int
    price: float
    status: str


class CreateBookingRequest(BaseModel):
    """Request to create a booking."""
    user_id: int = Field(..., gt=0, description="User ID")
    flight_id: int = Field(..., gt=0, description="Flight ID")
    passenger_name: str = Field(..., min_length=1, max_length=200, description="Passenger name")
    passenger_email: EmailStr = Field(..., description="Passenger email")
    seat_count: int = Field(..., gt=0, description="Number of seats to book")


class BookingResponse(BaseModel):
    """Booking response."""
    id: int
    booking_id: str
    user_id: int
    flight_id: int
    passenger_name: str
    passenger_email: str
    seat_count: int
    total_price: float
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CancelBookingResponse(BaseModel):
    """Response for booking cancellation."""
    success: bool
    message: str
    booking: Optional[BookingResponse] = None


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
