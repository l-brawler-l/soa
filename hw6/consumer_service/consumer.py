"""Kafka consumer with at-least-once semantics, DLQ support, and monitoring.

Implements:
- Consumer group with manual offset commit (at-least-once)
- Dead Letter Queue for failed events
- Prometheus metrics (lag, throughput, errors)
- Protobuf deserialization
"""

import json
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

from confluent_kafka import Consumer, Producer, KafkaError, KafkaException, TopicPartition

from consumer_service.config import Config
from consumer_service.database import CassandraClient
from consumer_service.event_handler import EventHandler, EventValidationError, EVENT_TYPE_NAMES
from consumer_service.metrics import (
    cassandra_connected,
    cassandra_write_errors_total,
    consumer_connected,
    consumer_lag,
    dlq_events_total,
    event_processing_duration_seconds,
    events_processed_total,
)
from consumer_service.proto import warehouse_events_pb2

logger = logging.getLogger(__name__)


class WarehouseConsumer:
    """Kafka consumer for warehouse events."""

    def __init__(self, config: Config, db: CassandraClient):
        self.config = config
        self.db = db
        self.handler = EventHandler(db)
        self._consumer: Optional[Consumer] = None
        self._dlq_producer: Optional[Producer] = None
        self._running = False

    def connect(self) -> None:
        """Initialize Kafka consumer and DLQ producer."""
        max_retries = 10
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                self._consumer = Consumer({
                    "bootstrap.servers": self.config.KAFKA_BOOTSTRAP_SERVERS,
                    "group.id": self.config.KAFKA_GROUP_ID,
                    "auto.offset.reset": "earliest",
                    "enable.auto.commit": False,  # Manual commit for at-least-once
                    "max.poll.interval.ms": 300000,
                    "session.timeout.ms": 30000,
                    "heartbeat.interval.ms": 10000,
                    "client.id": "warehouse-consumer",
                })

                # DLQ producer
                self._dlq_producer = Producer({
                    "bootstrap.servers": self.config.KAFKA_BOOTSTRAP_SERVERS,
                    "acks": "all",
                    "client.id": "warehouse-dlq-producer",
                })

                # Subscribe to topic
                self._consumer.subscribe([self.config.KAFKA_TOPIC])

                # Test connectivity
                self._consumer.list_topics(timeout=10)
                consumer_connected.set(1)

                logger.info(
                    "Kafka consumer connected: servers=%s, group=%s, topic=%s",
                    self.config.KAFKA_BOOTSTRAP_SERVERS,
                    self.config.KAFKA_GROUP_ID,
                    self.config.KAFKA_TOPIC,
                )
                return
            except Exception as e:
                logger.warning(
                    "Failed to connect to Kafka (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

        raise ConnectionError("Failed to connect to Kafka after retries")

    @property
    def is_connected(self) -> bool:
        return self._consumer is not None

    def run(self) -> None:
        """Main consumer loop. Runs until stopped."""
        self._running = True
        logger.info("Consumer loop started")

        while self._running:
            try:
                msg = self._consumer.poll(timeout=1.0)

                if msg is None:
                    self._update_lag_metrics()
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug(
                            "End of partition: %s [%d] at offset %d",
                            msg.topic(), msg.partition(), msg.offset(),
                        )
                    else:
                        logger.error("Kafka error: %s", msg.error())
                    continue

                # Process the message
                self._process_message(msg)

            except KafkaException as e:
                logger.error("Kafka exception: %s", e)
                consumer_connected.set(0)
                time.sleep(1)
            except Exception as e:
                logger.error("Unexpected error in consumer loop: %s", e)
                time.sleep(1)

        logger.info("Consumer loop stopped")

    def stop(self) -> None:
        """Stop the consumer loop."""
        self._running = False
        if self._consumer:
            self._consumer.close()
            consumer_connected.set(0)
        if self._dlq_producer:
            self._dlq_producer.flush(10)
        logger.info("Consumer stopped")

    def _process_message(self, msg) -> None:
        """Process a single Kafka message."""
        partition = msg.partition()
        offset = msg.offset()
        start_time = time.time()

        try:
            # Deserialize protobuf
            pb_event = warehouse_events_pb2.WarehouseEvent()
            pb_event.ParseFromString(msg.value())

            event_type = EVENT_TYPE_NAMES.get(pb_event.event_type, "UNKNOWN")

            logger.info(
                "Received event: event_id=%s, event_type=%s, offset=%d, partition=%d",
                pb_event.event_id, event_type, offset, partition,
            )

            # Process the event
            self.handler.process_event(pb_event)

            # Commit offset AFTER successful processing (at-least-once)
            self._consumer.commit(msg)

            # Update metrics
            duration = time.time() - start_time
            events_processed_total.labels(event_type=event_type).inc()
            event_processing_duration_seconds.observe(duration)

            logger.info(
                "Event processed: event_id=%s, event_type=%s, duration=%.3fs",
                pb_event.event_id, event_type, duration,
            )

        except EventValidationError as e:
            # Validation error → send to DLQ, commit offset (don't retry)
            logger.warning(
                "Validation error for event at partition=%d offset=%d: %s",
                partition, offset, e,
            )
            self._send_to_dlq(msg, str(e), "VALIDATION_ERROR")
            self._consumer.commit(msg)
            dlq_events_total.labels(reason="VALIDATION_ERROR").inc()

        except Exception as e:
            # Unexpected error → send to DLQ, commit offset
            logger.error(
                "Error processing event at partition=%d offset=%d: %s\n%s",
                partition, offset, e, traceback.format_exc(),
            )
            self._send_to_dlq(msg, str(e), "PROCESSING_ERROR")
            cassandra_write_errors_total.inc()

            # Still commit to avoid blocking the consumer
            try:
                self._consumer.commit(msg)
            except Exception:
                pass

            dlq_events_total.labels(reason="PROCESSING_ERROR").inc()

    def _send_to_dlq(self, msg, error_reason: str, error_code: str) -> None:
        """Send a failed message to the Dead Letter Queue topic."""
        if not self._dlq_producer:
            logger.error("DLQ producer not available")
            return

        try:
            # Try to deserialize for logging
            original_event = {}
            try:
                pb_event = warehouse_events_pb2.WarehouseEvent()
                pb_event.ParseFromString(msg.value())
                original_event = {
                    "event_id": pb_event.event_id,
                    "event_type": EVENT_TYPE_NAMES.get(pb_event.event_type, "UNKNOWN"),
                    "product_id": pb_event.product_id,
                    "zone_id": pb_event.zone_id,
                    "quantity": pb_event.quantity,
                    "order_id": pb_event.order_id,
                    "sequence_number": pb_event.sequence_number,
                }
            except Exception:
                original_event = {"raw": msg.value().hex() if msg.value() else ""}

            dlq_message = {
                "original_event": original_event,
                "error_reason": error_reason,
                "error_code": error_code,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "kafka_metadata": {
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                    "topic": msg.topic(),
                },
            }

            self._dlq_producer.produce(
                topic=self.config.KAFKA_DLQ_TOPIC,
                key=msg.key(),
                value=json.dumps(dlq_message).encode("utf-8"),
            )
            self._dlq_producer.flush(timeout=5)

            logger.info(
                "Event sent to DLQ: partition=%d, offset=%d, reason=%s",
                msg.partition(), msg.offset(), error_code,
            )
        except Exception as e:
            logger.error("Failed to send event to DLQ: %s", e)

    def _update_lag_metrics(self) -> None:
        """Update consumer lag metrics."""
        try:
            if not self._consumer:
                return

            # Get assigned partitions
            assignment = self._consumer.assignment()
            if not assignment:
                return

            # Get committed offsets
            committed = self._consumer.committed(assignment, timeout=5)

            # Get high watermarks
            for tp in assignment:
                try:
                    low, high = self._consumer.get_watermark_offsets(tp, timeout=5)
                    committed_offset = 0
                    for c in committed:
                        if c.partition == tp.partition and c.offset >= 0:
                            committed_offset = c.offset
                            break

                    lag = max(0, high - committed_offset)
                    consumer_lag.labels(partition=str(tp.partition)).set(lag)
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Failed to update lag metrics: %s", e)
