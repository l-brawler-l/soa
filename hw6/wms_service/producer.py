"""Kafka producer with protobuf serialization and retry logic."""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from confluent_kafka import Producer
from google.protobuf.timestamp_pb2 import Timestamp

from wms_service.config import Config
from wms_service.proto import warehouse_events_pb2

logger = logging.getLogger(__name__)

# Mapping from string enum to protobuf enum
EVENT_TYPE_MAP = {
    "PRODUCT_RECEIVED": warehouse_events_pb2.PRODUCT_RECEIVED,
    "PRODUCT_SHIPPED": warehouse_events_pb2.PRODUCT_SHIPPED,
    "PRODUCT_MOVED": warehouse_events_pb2.PRODUCT_MOVED,
    "PRODUCT_RESERVED": warehouse_events_pb2.PRODUCT_RESERVED,
    "PRODUCT_RELEASED": warehouse_events_pb2.PRODUCT_RELEASED,
    "INVENTORY_COUNTED": warehouse_events_pb2.INVENTORY_COUNTED,
    "ORDER_CREATED": warehouse_events_pb2.ORDER_CREATED,
    "ORDER_COMPLETED": warehouse_events_pb2.ORDER_COMPLETED,
}


class WarehouseEventProducer:
    """Kafka producer for warehouse events with protobuf serialization."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._producer: Optional[Producer] = None
        self._connected = False
        self._sequence_counter = 0

    def connect(self) -> None:
        """Initialize Kafka producer with retry."""
        max_retries = 5
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                self._producer = Producer({
                    "bootstrap.servers": self.config.KAFKA_BOOTSTRAP_SERVERS,
                    "acks": "all",
                    "retries": 5,
                    "retry.backoff.ms": 500,
                    "delivery.timeout.ms": 30000,
                    "linger.ms": 10,
                    "batch.size": 16384,
                    "compression.type": "snappy",
                    "client.id": "wms-service-producer",
                })
                # Test connectivity by requesting metadata
                self._producer.list_topics(timeout=10)
                self._connected = True
                logger.info("Kafka producer connected to %s", self.config.KAFKA_BOOTSTRAP_SERVERS)
                return
            except Exception as e:
                logger.warning(
                    "Failed to connect to Kafka (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff *= 2

        raise ConnectionError("Failed to connect to Kafka after retries")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _delivery_callback(self, err, msg):
        """Callback for delivery reports."""
        if err:
            logger.error("Message delivery failed: %s", err)
        else:
            logger.debug(
                "Message delivered to %s [%d] at offset %d",
                msg.topic(), msg.partition(), msg.offset(),
            )

    def _next_sequence(self) -> int:
        """Get next monotonic sequence number."""
        self._sequence_counter += 1
        return self._sequence_counter

    def publish_event(
        self,
        event_type: str,
        product_id: str = "",
        zone_id: str = "",
        quantity: int = 0,
        to_zone_id: str = "",
        order_id: str = "",
        items: Optional[List[Dict]] = None,
        supplier_id: str = "",
        event_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        sequence_number: Optional[int] = None,
    ) -> str:
        """
        Publish a warehouse event to Kafka.

        Serializes the event as protobuf and sends to Kafka.
        Returns the event_id.
        """
        if not self._producer:
            raise RuntimeError("Producer not connected. Call connect() first.")

        event_id = event_id or str(uuid4())
        timestamp = timestamp or datetime.now(timezone.utc)
        sequence_number = sequence_number or self._next_sequence()

        # Build protobuf message
        pb_event = warehouse_events_pb2.WarehouseEvent()
        pb_event.event_id = event_id
        pb_event.event_type = EVENT_TYPE_MAP.get(
            event_type, warehouse_events_pb2.EVENT_TYPE_UNSPECIFIED
        )

        ts = Timestamp()
        ts.FromDatetime(timestamp)
        pb_event.timestamp.CopyFrom(ts)

        pb_event.sequence_number = sequence_number
        pb_event.product_id = product_id
        pb_event.zone_id = zone_id
        pb_event.quantity = quantity
        pb_event.to_zone_id = to_zone_id
        pb_event.order_id = order_id
        pb_event.supplier_id = supplier_id

        if items:
            for item in items:
                pb_item = pb_event.items.add()
                pb_item.product_id = item["product_id"]
                pb_item.zone_id = item["zone_id"]
                pb_item.quantity = item["quantity"]

        # Serialize to protobuf bytes
        serialized = pb_event.SerializeToString()

        # Partition key: product_id for product events, order_id for order events
        partition_key = product_id or order_id or event_id

        max_retries = 3
        backoff = 0.5

        for attempt in range(max_retries):
            try:
                self._producer.produce(
                    topic=self.config.KAFKA_TOPIC,
                    key=partition_key.encode("utf-8"),
                    value=serialized,
                    callback=self._delivery_callback,
                )
                self._producer.poll(0)
                logger.info(
                    "Published event: event_id=%s, event_type=%s, timestamp=%s",
                    event_id, event_type, timestamp.isoformat(),
                )
                return event_id
            except BufferError:
                logger.warning(
                    "Producer buffer full, retrying (attempt %d/%d)",
                    attempt + 1, max_retries,
                )
                self._producer.poll(1)
                time.sleep(backoff)
                backoff *= 2
            except Exception as e:
                logger.error(
                    "Failed to publish event (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff *= 2

        raise RuntimeError(f"Failed to publish event {event_id} after {max_retries} retries")

    def flush(self, timeout: float = 10.0) -> None:
        """Flush pending messages."""
        if self._producer:
            self._producer.flush(timeout)

    def close(self) -> None:
        """Flush and close the producer."""
        if self._producer:
            self._producer.flush(30)
            self._connected = False
            logger.info("Kafka producer closed")
