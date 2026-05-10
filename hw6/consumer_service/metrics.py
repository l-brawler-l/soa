"""Prometheus metrics for the consumer service."""

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST


# Counter: total events processed, labeled by event_type
events_processed_total = Counter(
    "events_processed_total",
    "Total number of events processed",
    ["event_type"],
)

# Histogram: event processing duration in seconds
event_processing_duration_seconds = Histogram(
    "event_processing_duration_seconds",
    "Time to process a single event in seconds",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# Counter: Cassandra write errors
cassandra_write_errors_total = Counter(
    "cassandra_write_errors_total",
    "Total number of Cassandra write errors",
)

# Gauge: consumer lag per partition
consumer_lag = Gauge(
    "consumer_lag",
    "Consumer lag (difference between latest offset and committed offset)",
    ["partition"],
)

# Counter: DLQ events
dlq_events_total = Counter(
    "dlq_events_total",
    "Total number of events sent to DLQ",
    ["reason"],
)

# Gauge: consumer connected status
consumer_connected = Gauge(
    "consumer_connected",
    "Whether the consumer is connected to Kafka (1=yes, 0=no)",
)

# Gauge: cassandra connected status
cassandra_connected = Gauge(
    "cassandra_connected",
    "Whether Cassandra is connected (1=yes, 0=no)",
)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest()


def get_content_type() -> str:
    """Get the content type for Prometheus metrics."""
    return CONTENT_TYPE_LATEST
