"""Movie Service - FastAPI application for publishing movie events to Kafka."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from movie_service.config import Config
from movie_service.generator import EventGenerator
from movie_service.producer import MovieEventProducer
from movie_service.schemas import (
    ErrorResponse,
    HealthResponse,
    MovieEventRequest,
    MovieEventResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

config = Config()
producer = MovieEventProducer(config)
generator: EventGenerator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect producer, start generator."""
    global generator

    logger.info("Starting Movie Service...")
    producer.connect()

    if config.GENERATOR_ENABLED:
        generator = EventGenerator(producer, config)
        generator.start()
        logger.info("Event generator started")

    yield

    # Shutdown
    if generator and generator.is_running:
        await generator.stop()
    producer.close()
    logger.info("Movie Service stopped")


app = FastAPI(
    title="Movie Service (Producer)",
    description="Publishes movie events to Kafka for the analytics pipeline",
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
    response_model=MovieEventResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def publish_event(event: MovieEventRequest):
    """
    Publish a movie event to Kafka.

    Accepts a JSON event, validates it against the protobuf schema,
    and publishes to the movie-events Kafka topic.
    """
    try:
        event_id = event.event_id or str(uuid4())
        timestamp = event.timestamp or datetime.now(timezone.utc)

        published_id = producer.publish_event(
            event_id=event_id,
            user_id=event.user_id,
            movie_id=event.movie_id,
            event_type=event.event_type.value,
            device_type=event.device_type.value,
            session_id=event.session_id,
            progress_seconds=event.progress_seconds,
            timestamp=timestamp,
        )
        # Flush to ensure the message is sent to Kafka immediately
        producer.flush(timeout=5.0)

        return MovieEventResponse(
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

    generator = EventGenerator(producer, config)
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
