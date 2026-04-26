# HW5: Online Cinema — Event Streaming + Analytics Pipeline

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Movie Service   │────▶│    Kafka      │────▶│   ClickHouse     │
│  (Producer)      │     │  (2 brokers)  │     │  (Kafka Engine   │
│  - HTTP API      │     │  + Schema     │     │   → MergeTree)   │
│  - Generator     │     │    Registry   │     │                  │
└─────────────────┘     └──────────────┘     └────────┬─────────┘
                                                       │
                                              ┌────────▼─────────┐
                                              │  Aggregation     │
                                              │  Service          │
                                              │  - DAU            │
                                              │  - Avg Duration   │
                                              │  - Top Movies     │
                                              │  - Conversion     │
                                              │  - Retention D1/7 │
                                              └──┬──────────┬────┘
                                                 │          │
                                        ┌────────▼──┐  ┌───▼────────┐
                                        │ PostgreSQL │  │   MinIO    │
                                        │ (metrics)  │  │   (S3)    │
                                        └────────┬──┘  └────────────┘
                                                 │
                                        ┌────────▼──┐
                                        │  Grafana   │
                                        │ (dashboards│
                                        └───────────┘
```

## Components

| Component | Port | Description |
|-----------|------|-------------|
| Movie Service | 8000 | HTTP API + event generator → Kafka |
| Aggregation Service | 8001 | Metrics computation + PostgreSQL + S3 export |
| Kafka Broker 1 | 9092 | Kafka cluster node 1 |
| Kafka Broker 2 | 9093 | Kafka cluster node 2 |
| Schema Registry | 8081 | Protobuf schema versioning |
| ClickHouse | 8123/9000 | Columnar DB for raw events + aggregates |
| PostgreSQL | 5432 | Metrics storage |
| MinIO | 9001/9002 | S3-compatible object storage |
| Grafana | 3000 | Analytics dashboards |

## Quick Start

```bash
# Start everything
docker-compose up -d --build

# Or use Makefile
make up
```

All services start automatically. The event generator begins producing synthetic data immediately.

## Event Schema (Protobuf)

Events are defined in `proto/movie_events.proto` and registered in Schema Registry.

**Partition key**: `user_id` — ensures all events from the same user land in the same partition, preserving per-user event ordering (important for session-based analytics like VIEW_STARTED → VIEW_FINISHED).

## API Endpoints

### Movie Service (port 8000)

- `GET /health` — Health check
- `POST /events` — Publish a movie event
- `POST /generator/start` — Start event generator
- `POST /generator/stop` — Stop event generator

### Aggregation Service (port 8001)

- `GET /health` — Health check
- `POST /compute?target_date=YYYY-MM-DD` — Trigger metrics computation
- `POST /export?target_date=YYYY-MM-DD` — Export metrics to S3
- `GET /metrics?target_date=YYYY-MM-DD` — Get stored metrics

## Business Metrics

| Metric | Description |
|--------|-------------|
| DAU | Unique users per day (`uniq(user_id)`) |
| Avg View Duration | Average `progress_seconds` for `VIEW_FINISHED` events |
| Top Movies | Movies ranked by view count |
| View Conversion | `VIEW_FINISHED / VIEW_STARTED` ratio |
| Retention D1, D7 | Users returning 1 and 7 days after first activity |
| Device Distribution | Events and users per device type |

## Database Migrations

- **PostgreSQL**: Alembic migrations in `alembic/versions/`. Applied automatically on service start.
- **ClickHouse**: SQL init scripts in `clickhouse/init/`. Applied automatically on container start.

## Running Tests

```bash
# Services must be running first
docker compose up -d --build

# Install test dependencies and run
pip install -r requirements-tests.txt
pytest tests/ -v

# Or use Makefile
make test
```

## Grafana Dashboard

Access at http://localhost:3000 (admin/admin).

http://localhost:3000/d/movie-analytics-main/movie-analytics-dashboard?orgId=1&from=now-30d&to=now

Panels:
1. **Retention Cohort Heatmap** — Cohort analysis table
2. **DAU** — Daily active users over time
3. **View Conversion Rate** — VIEW_FINISHED/VIEW_STARTED %
4. **Top 10 Movies** — Bar chart of most viewed movies
5. **Average View Duration** — Time series
6. **Device Distribution** — Pie chart

## Kafka Cluster

- 2 brokers with KRaft (no ZooKeeper)
- Topic `movie-events`: 3 partitions, replication factor 2
- `min.insync.replicas = 1`
- Schema Registry with Protobuf schema versioning
- Health checks on all components

## S3 Export

Daily metrics exported to MinIO:
- Bucket: `movie-analytics`
- Path: `daily/YYYY-MM-DD/aggregates.json`
- Format: JSON with all metrics for the day
- Idempotent: re-export overwrites existing file
