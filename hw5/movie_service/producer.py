"""Kafka producer with protobuf serialization and retry logic."""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from confluent_kafka import Producer
from confluent_kafka.serialization import SerializationContext, MessageField
from google.protobuf.timestamp_pb2 import Timestamp

from movie_service.config import Config
from movie_service.proto import movie_events_pb2

logger = logging.getLogger(__name__)


# Mapping from string enum to protobuf enum
EVENT_TYPE_MAP = {
    "VIEW_STARTED": movie_events_pb2.VIEW_STARTED,
    "VIEW_FINISHED": movie_events_pb2.VIEW_FINISHED,
    "VIEW_PAUSED": movie_events_pb2.VIEW_PAUSED,
    "VIEW_RESUMED": movie_events_pb2.VIEW_RESUMED,
    "LIKED": movie_events_pb2.LIKED,
    "SEARCHED": movie_events_pb2.SEARCHED,
}

DEVICE_TYPE_MAP = {
    "MOBILE": movie_events_pb2.MOBILE,
    "DESKTOP": movie_events_pb2.DESKTOP,
    "TV": movie_events_pb2.TV,
    "TABLET": movie_events_pb2.TABLET,
}


class MovieEventProducer:
    """Kafka producer for movie events with protobuf serialization."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._producer: Optional[Producer] = None
        self._connected = False

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
                    "client.id": "movie-service-producer",
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

    def publish_event(
        self,
        user_id: str,
        movie_id: str,
        event_type: str,
        device_type: str,
        session_id: str,
        progress_seconds: int = 0,
        event_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """
        Publish a movie event to Kafka.

        Serializes the event as protobuf, sends as JSON to Kafka
        (for ClickHouse JSONEachRow compatibility), and also validates
        against the protobuf schema.

        Returns the event_id.
        """
        if not self._producer:
            raise RuntimeError("Producer not connected. Call connect() first.")

        event_id = event_id or str(uuid4())
        timestamp = timestamp or datetime.now(timezone.utc)

        # Validate via protobuf
        pb_event = movie_events_pb2.MovieEvent()
        pb_event.event_id = event_id
        pb_event.user_id = user_id
        pb_event.movie_id = movie_id
        pb_event.event_type = EVENT_TYPE_MAP.get(event_type, movie_events_pb2.EVENT_TYPE_UNSPECIFIED)
        pb_event.device_type = DEVICE_TYPE_MAP.get(device_type, movie_events_pb2.DEVICE_TYPE_UNSPECIFIED)
        pb_event.session_id = session_id
        pb_event.progress_seconds = progress_seconds

        ts = Timestamp()
        ts.FromDatetime(timestamp)
        pb_event.timestamp.CopyFrom(ts)

        # Validate by serializing (will raise if invalid)
        pb_event.SerializeToString()

        # Send as JSON for ClickHouse Kafka Engine (JSONEachRow format)
        event_json = {
            "event_id": event_id,
            "user_id": user_id,
            "movie_id": movie_id,
            "event_type": event_type,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "device_type": device_type,
            "session_id": session_id,
            "progress_seconds": progress_seconds,
        }

        max_retries = 3
        backoff = 0.5

        for attempt in range(max_retries):
            try:
                self._producer.produce(
                    topic=self.config.KAFKA_TOPIC,
                    key=user_id.encode("utf-8"),  # Partition by user_id
                    value=json.dumps(event_json).encode("utf-8"),
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
