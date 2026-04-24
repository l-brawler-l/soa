"""Pydantic schemas for request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EventType(str, Enum):
    VIEW_STARTED = "VIEW_STARTED"
    VIEW_FINISHED = "VIEW_FINISHED"
    VIEW_PAUSED = "VIEW_PAUSED"
    VIEW_RESUMED = "VIEW_RESUMED"
    LIKED = "LIKED"
    SEARCHED = "SEARCHED"


class DeviceType(str, Enum):
    MOBILE = "MOBILE"
    DESKTOP = "DESKTOP"
    TV = "TV"
    TABLET = "TABLET"


class MovieEventRequest(BaseModel):
    """Request schema for publishing a movie event."""

    event_id: Optional[str] = Field(None, description="UUID, auto-generated if not provided")
    user_id: str = Field(..., min_length=1, description="User identifier")
    movie_id: str = Field(..., min_length=1, description="Movie identifier")
    event_type: EventType = Field(..., description="Type of user action")
    timestamp: Optional[datetime] = Field(None, description="Event time UTC, auto-set if not provided")
    device_type: DeviceType = Field(..., description="Device used")
    session_id: str = Field(..., min_length=1, description="Session identifier")
    progress_seconds: int = Field(0, ge=0, description="View progress in seconds")


class MovieEventResponse(BaseModel):
    """Response after publishing an event."""

    event_id: str
    status: str = "published"
    message: str = "Event published successfully"


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    kafka_connected: bool
    generator_running: bool
