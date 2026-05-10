# Smart Warehouse: Event-Driven State Management with Cassandra

## Architecture

```
+---------------+   +-----------+   +------------------+
|  WMS Service  |-->|   Kafka   |-->| Consumer Service |
|  (Producer)   |   | (Events)  |   +------------------+
+---------------+   +-----------+            |
                                             |
        +--------------------------+---------+------------------+
        |                          |                            |
        v                          v                            v
   +----------+             +-------------+       +----------------------+
   | DLQ Topic|             | Cassandra   |       | Prometheus + Grafana |
   | (Errors) |             |  (3-node)   |       +----------------------+
   +----------+             +-------------+
```

### Components

- **WMS Service (Producer)** — FastAPI service that generates warehouse events and publishes them to Kafka topic `warehouse-events`. Supports HTTP API for manual event submission and an automatic event generator.
- **Kafka (2 brokers, KRaft)** — Message broker with Schema Registry for Protobuf schema versioning. Topics: `warehouse-events` (3 partitions, RF=2) and `warehouse-events-dlq`.
- **Consumer Service** — Reads events from Kafka, processes them, and updates state in Cassandra. Provides `/health` and `/metrics` endpoints for monitoring.
- **Cassandra (3-node cluster)** — Distributed database for warehouse state. Uses `NetworkTopologyStrategy` with `replication_factor=3`.
- **Prometheus + Grafana** — Monitoring stack with dashboards for consumer lag, throughput, and errors.

## Quick Start

```bash
# Start all services
docker-compose up -d --build

# Or use Makefile
make up

# Check health
make health

# Run tests (services must be running)
make test
```

## Cassandra Data Model

### Design Rationale

Tables are designed **for query patterns** (Cassandra best practice). We use denormalization to support different access patterns efficiently.

#### Table 1: `inventory_by_product_zone`
- **Query**: Get inventory for a specific product in a specific zone
- **Partition Key**: `product_id` — groups all zones for a product
- **Clustering Key**: `zone_id` — allows filtering by zone within a partition
- **Use case**: `SELECT * FROM inventory_by_product_zone WHERE product_id = ? AND zone_id = ?`

#### Table 2: `inventory_by_product`
- **Query**: Get all inventory for a product across all zones
- **Partition Key**: `product_id`
- **Clustering Key**: `zone_id`
- **Use case**: `SELECT * FROM inventory_by_product WHERE product_id = ?`

#### Table 3: `inventory_by_zone`
- **Query**: Get all products in a zone
- **Partition Key**: `zone_id` — groups all products in a zone
- **Clustering Key**: `product_id`
- **Use case**: `SELECT * FROM inventory_by_zone WHERE zone_id = ?`

#### Table 4: `orders`
- **Query**: Get order by ID
- **Partition Key**: `order_id`

#### Table 5: `event_log` (audit trail)
- **Query**: Get event history for a product
- **Partition Key**: `product_id`
- **Clustering Key**: `(event_timestamp DESC, event_id)` — time-ordered

#### Table 6: `processed_events` (idempotency)
- **Partition Key**: `event_id`
- **TTL**: 7 days (automatic cleanup)

#### Table 7: `entity_timestamps` (out-of-order handling)
- **Partition Key**: `entity_key` (e.g., `product_id:zone_id`)

### Consistency Levels

- **Writes**: `QUORUM` — guarantees data is written to majority of nodes (2 out of 3). This ensures durability even if one node fails.
- **Reads**: `ONE` — reads from the nearest replica for low latency. This is acceptable because:
  - Our writes use QUORUM, so data is always on at least 2 nodes
  - For inventory queries, eventual consistency is acceptable (slight delay is OK)
  - For idempotency checks, even if we read stale data, the worst case is processing an event twice (which the batch ensures is atomic)
  - Trade-off: faster reads at the cost of potentially reading slightly stale data

## Event Processing

### At-Least-Once Semantics
- Consumer uses manual offset commit (`enable.auto.commit=false`)
- Offset is committed **only after** successful processing and Cassandra write
- On restart, processing continues from the last committed offset

### Idempotency
- Each event has a unique `event_id`
- Before processing, consumer checks `processed_events` table
- If event was already processed, it's skipped
- The `processed_events` table has a 7-day TTL for automatic cleanup

### Consistent Batch Updates
- All denormalized tables are updated in a single **Cassandra logged batch**
- This ensures atomicity: either all tables are updated or none
- No partial updates possible

### Out-of-Order Event Handling
- Each event has a `sequence_number` (monotonic)
- The `entity_timestamps` table tracks the last processed sequence per entity
- Events with sequence ≤ last processed are ignored
- Falls back to timestamp comparison if sequence numbers are not available

### Dead Letter Queue (DLQ)
- Invalid events (validation errors) are sent to `warehouse-events-dlq` topic
- Processing errors also go to DLQ
- DLQ messages include: original event, error reason, error code, timestamp, Kafka metadata
- Consumer continues processing after DLQ send (never blocks)

## Schema Evolution (Protobuf)

### Strategy: Backward Compatible

Protobuf is inherently backward compatible:
- New fields with default values can be added without breaking existing consumers
- Old messages (V1) can be deserialized by new code (V2) — new fields get default values
- New messages (V2) can be deserialized by old code (V1) — unknown fields are ignored

### V1 → V2 Evolution

**V1 Schema** (original):
```protobuf
message WarehouseEvent {
  string event_id = 1;
  EventType event_type = 2;
  Timestamp timestamp = 3;
  int64 sequence_number = 4;
  string product_id = 5;
  string zone_id = 6;
  int32 quantity = 7;
  string to_zone_id = 8;
  string order_id = 9;
  repeated OrderItem items = 10;
}
```

**V2 Schema** (with `supplier_id`):
```protobuf
message WarehouseEvent {
  // ... all V1 fields ...
  string supplier_id = 11;  // NEW: supplier identifier
}
```

### How to Add a New Version

1. Add the new field to `proto/warehouse_events.proto` with a new field number
2. Ensure the field has a default value (empty string for `string`, 0 for `int32`, etc.)
3. Register the new schema in Schema Registry:
   ```bash
   curl -X POST http://localhost:8081/subjects/warehouse-events-value/versions \
     -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
     -d '{"schemaType": "PROTOBUF", "schema": "..."}'
   ```
4. Add the new column to Cassandra tables (ALTER TABLE ... ADD ...)
5. Update the consumer's event handler to use the new field
6. V1 events will have the default value for the new field

### Consumer Handling

The consumer explicitly handles both versions:
- V1 events: `supplier_id` is empty string (protobuf default)
- V2 events: `supplier_id` contains the actual supplier ID
- Both are stored in Cassandra (the `supplier_id` column was added via migration)

## Fault Tolerance Demo

### Cassandra Node Failure

```bash
# Check cluster status (3 nodes UN = Up/Normal)
docker exec cassandra-1 nodetool status

# Stop one node
docker stop cassandra-2

# Send events — they should still be processed (QUORUM = 2/3 nodes)
make test-event

# Verify data
make query-inventory

# Restart the node
docker start cassandra-2

# Verify node rejoins
docker exec cassandra-1 nodetool status
```

### Consistency Level Comparison

| CL | Nodes Required | With 1 Node Down | Latency |
|----|---------------|-------------------|---------|
| ONE | 1 | ✅ Works | Low |
| QUORUM | 2 | ✅ Works (2/3) | Medium |
| ALL | 3 | ❌ Fails | High |

## Monitoring

### Endpoints

- **Health**: `GET http://localhost:8001/health` — Returns 200 if Kafka + Cassandra connected, 503 otherwise
- **Metrics**: `GET http://localhost:8001/metrics` — Prometheus-format metrics

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `consumer_lag` | Gauge | Lag per partition |
| `events_processed_total` | Counter | Events processed by type |
| `event_processing_duration_seconds` | Histogram | Processing time |
| `cassandra_write_errors_total` | Counter | Cassandra write errors |
| `dlq_events_total` | Counter | Events sent to DLQ |

### Grafana Dashboard

Access at `http://localhost:3000` (admin/admin). Dashboard panels:
1. **Consumer Lag by Partition** — shows lag per Kafka partition
2. **Events Processed per Second** — throughput by event type
3. **Cassandra Write Errors & DLQ Events** — error rates
4. **Event Processing Duration** — p50, p95, p99 latencies

## API Reference

### WMS Service (Port 8000)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/events` | Publish warehouse event |
| POST | `/generator/start` | Start event generator |
| POST | `/generator/stop` | Stop event generator |

### Consumer Service (Port 8001)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (200/503) |
| GET | `/metrics` | Prometheus metrics |
| GET | `/inventory/{product_id}` | Get product inventory |
| GET | `/inventory/{product_id}/{zone_id}` | Get inventory in zone |
| GET | `/zone/{zone_id}` | Get zone inventory |
| GET | `/order/{order_id}` | Get order details |

## Testing

```bash
# Start services
make up

# Wait for services to be ready (~2 minutes for Cassandra cluster)
make health

# Run all tests
make test

# Run specific test class
cd .. && python3 -m pytest hw6/tests/test_warehouse.py::TestIdempotency -v
```
