"""Pydantic schemas for request/response validation."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    PRODUCT_RECEIVED = "PRODUCT_RECEIVED"
    PRODUCT_SHIPPED = "PRODUCT_SHIPPED"
    PRODUCT_MOVED = "PRODUCT_MOVED"
    PRODUCT_RESERVED = "PRODUCT_RESERVED"
    PRODUCT_RELEASED = "PRODUCT_RELEASED"
    INVENTORY_COUNTED = "INVENTORY_COUNTED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_COMPLETED = "ORDER_COMPLETED"


class OrderItemSchema(BaseModel):
    """Order item within an order event."""

    product_id: str = Field(..., min_length=1, description="Product SKU")
    zone_id: str = Field(..., min_length=1, description="Zone identifier")
    quantity: int = Field(..., gt=0, description="Quantity")


class WarehouseEventRequest(BaseModel):
    """Request schema for publishing a warehouse event."""

    event_id: Optional[str] = Field(None, description="UUID, auto-generated if not provided")
    event_type: EventType = Field(..., description="Type of warehouse operation")
    timestamp: Optional[datetime] = Field(None, description="Event time UTC, auto-set if not provided")
    sequence_number: Optional[int] = Field(None, description="Sequence number for ordering")

    product_id: Optional[str] = Field(None, description="Product SKU")
    zone_id: Optional[str] = Field(None, description="Zone identifier (source zone for MOVE)")
    quantity: Optional[int] = Field(None, description="Quantity affected")

    to_zone_id: Optional[str] = Field(None, description="Destination zone for MOVE")

    order_id: Optional[str] = Field(None, description="Order identifier")
    items: Optional[List[OrderItemSchema]] = Field(None, description="Order line items")

    # V2 field
    supplier_id: Optional[str] = Field(None, description="Supplier identifier (V2)")


class WarehouseEventResponse(BaseModel):
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
