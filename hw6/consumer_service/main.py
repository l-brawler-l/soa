"""Consumer Service - FastAPI app with Kafka consumer, health/metrics endpoints."""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, JSONResponse

from consumer_service.config import Config
from consumer_service.consumer import WarehouseConsumer
from consumer_service.database import CassandraClient
from consumer_service.metrics import (
    cassandra_connected,
    consumer_connected,
    get_content_type,
    get_metrics,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

config = Config()
db = CassandraClient(config)
consumer: WarehouseConsumer | None = None
consumer_thread: threading.Thread | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: connect to Cassandra, start consumer."""
    global consumer, consumer_thread

    logger.info("Starting Consumer Service...")

    # Connect to Cassandra and run migrations
    db.connect()
    db.run_migrations()
    cassandra_connected.set(1)

    # Create and start consumer
    consumer = WarehouseConsumer(config, db)
    consumer.connect()

    # Run consumer in a background thread
    consumer_thread = threading.Thread(target=consumer.run, daemon=True, name="kafka-consumer")
    consumer_thread.start()
    logger.info("Kafka consumer thread started")

    yield

    # Shutdown
    if consumer:
        consumer.stop()
    if consumer_thread:
        consumer_thread.join(timeout=10)
    db.close()
    cassandra_connected.set(0)
    consumer_connected.set(0)
    logger.info("Consumer Service stopped")


app = FastAPI(
    title="Consumer Service",
    description="Warehouse event consumer with Cassandra state management",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """
    Health endpoint for liveness/readiness probes.
    Returns 200 OK if consumer is connected to Kafka and Cassandra is available.
    Returns 503 Service Unavailable if one of the connections is lost.
    """
    kafka_ok = consumer is not None and consumer.is_connected
    cassandra_ok = db.is_connected

    if kafka_ok and cassandra_ok:
        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "kafka_connected": True,
                "cassandra_connected": True,
            },
        )
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "kafka_connected": kafka_ok,
                "cassandra_connected": cassandra_ok,
            },
        )


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    return PlainTextResponse(
        content=get_metrics(),
        media_type=get_content_type(),
    )


@app.get("/inventory/{product_id}")
async def get_inventory(product_id: str):
    """Get inventory for a product across all zones."""
    rows = db.get_inventory_by_product(product_id)
    total_available = sum(r["available_quantity"] for r in rows)
    total_reserved = sum(r["reserved_quantity"] for r in rows)
    return {
        "product_id": product_id,
        "total_available": total_available,
        "total_reserved": total_reserved,
        "zones": rows,
    }


@app.get("/inventory/{product_id}/{zone_id}")
async def get_inventory_by_zone(product_id: str, zone_id: str):
    """Get inventory for a product in a specific zone."""
    row = db.get_inventory_by_product_zone(product_id, zone_id)
    if row:
        return row
    return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/zone/{zone_id}")
async def get_zone_inventory(zone_id: str):
    """Get all products in a zone."""
    rows = db.get_inventory_by_zone(zone_id)
    return {"zone_id": zone_id, "products": rows}


@app.get("/order/{order_id}")
async def get_order(order_id: str):
    """Get order by ID."""
    order = db.get_order(order_id)
    if order:
        return order
    return JSONResponse(status_code=404, content={"error": "Order not found"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
