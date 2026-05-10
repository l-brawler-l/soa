"""WMS Service - FastAPI application for publishing warehouse events to Kafka."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from wms_service.config import Config
from wms_service.generator import WarehouseGenerator
from wms_service.producer import WarehouseEventProducer
from wms_service.schemas import (
    ErrorResponse,
    HealthResponse,
    WarehouseEventRequest,
    WarehouseEventResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

config = Config()
producer = WarehouseEventProducer(config)
generator: WarehouseGenerator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect producer, start generator."""
    global generator

    logger.info("Starting WMS Service...")
    producer.connect()

    if config.GENERATOR_ENABLED:
        generator = WarehouseGenerator(producer, config)
        generator.start()
        logger.info("Event generator started")

    yield

    # Shutdown
    if generator and generator.is_running:
        await generator.stop()
    producer.close()
    logger.info("WMS Service stopped")


app = FastAPI(
    title="WMS Service (Producer)",
    description="Publishes warehouse events to Kafka",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if producer.is_connected else "unhealthy",
        kafka_connected=producer.is_connected,
        generator_running=generator.is_running if generator else False,
    )


@app.post(
    "/events",
    response_model=WarehouseEventResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def publish_event(event: WarehouseEventRequest):
    """
    Publish a warehouse event to Kafka.

    Accepts a JSON event, validates it against the protobuf schema,
    and publishes to the warehouse-events Kafka topic.
    """
    try:
        event_id = event.event_id or str(uuid4())
        timestamp = event.timestamp or datetime.now(timezone.utc)

        items = None
        if event.items:
            items = [
                {
                    "product_id": item.product_id,
                    "zone_id": item.zone_id,
                    "quantity": item.quantity,
                }
                for item in event.items
            ]

        published_id = producer.publish_event(
            event_id=event_id,
            event_type=event.event_type.value,
            product_id=event.product_id or "",
            zone_id=event.zone_id or "",
            quantity=event.quantity or 0,
            to_zone_id=event.to_zone_id or "",
            order_id=event.order_id or "",
            items=items,
            supplier_id=event.supplier_id or "",
            timestamp=timestamp,
            sequence_number=event.sequence_number,
        )
        # Flush to ensure the message is sent to Kafka immediately
        producer.flush(timeout=5.0)

        return WarehouseEventResponse(
            event_id=published_id,
            status="published",
            message="Event published successfully",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to publish event: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to publish event: {e}")


@app.post("/generator/start")
async def start_generator():
    """Start the event generator manually."""
    global generator
    if generator and generator.is_running:
        return {"status": "already_running"}

    generator = WarehouseGenerator(producer, config)
    generator.start()
    return {"status": "started"}


@app.post("/generator/stop")
async def stop_generator():
    """Stop the event generator."""
    global generator
    if generator and generator.is_running:
        await generator.stop()
        return {"status": "stopped"}
    return {"status": "not_running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
