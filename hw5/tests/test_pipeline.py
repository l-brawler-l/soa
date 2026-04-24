"""Integration tests for the full event pipeline.

Tests the complete flow:
1. Publish event via Movie Service HTTP API
2. Verify event appears in ClickHouse
3. Verify aggregation computes metrics
4. Verify metrics stored in PostgreSQL
5. Verify S3 export works
"""

import json
import time
import uuid
from datetime import datetime, timezone

import clickhouse_connect
import psycopg2
import psycopg2.extras
import pytest
import requests
from minio import Minio

from tests.conftest import (
    AGGREGATION_SERVICE_URL,
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MOVIE_SERVICE_URL,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)


class TestMovieServiceHealth:
    """Test Movie Service health endpoint."""

    def test_health_check(self):
        """Movie Service should be healthy."""
        resp = requests.get(f"{MOVIE_SERVICE_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["kafka_connected"] is True


class TestAggregationServiceHealth:
    """Test Aggregation Service health endpoint."""

    def test_health_check(self):
        """Aggregation Service should be healthy."""
        resp = requests.get(f"{AGGREGATION_SERVICE_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["clickhouse_connected"] is True
        assert data["postgres_connected"] is True


class TestEventPublishing:
    """Test event publishing via HTTP API."""

    def test_publish_valid_event(self):
        """Should successfully publish a valid event."""
        event = {
            "user_id": "test_user_001",
            "movie_id": "test_movie_001",
            "event_type": "VIEW_STARTED",
            "device_type": "DESKTOP",
            "session_id": str(uuid.uuid4()),
            "progress_seconds": 0,
        }

        resp = requests.post(f"{MOVIE_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "published"
        assert "event_id" in data

    def test_publish_event_with_custom_id(self):
        """Should accept a custom event_id."""
        custom_id = str(uuid.uuid4())
        event = {
            "event_id": custom_id,
            "user_id": "test_user_002",
            "movie_id": "test_movie_002",
            "event_type": "LIKED",
            "device_type": "MOBILE",
            "session_id": str(uuid.uuid4()),
            "progress_seconds": 0,
        }

        resp = requests.post(f"{MOVIE_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == custom_id

    def test_publish_invalid_event_type(self):
        """Should reject invalid event type."""
        event = {
            "user_id": "test_user_003",
            "movie_id": "test_movie_003",
            "event_type": "INVALID_TYPE",
            "device_type": "DESKTOP",
            "session_id": str(uuid.uuid4()),
            "progress_seconds": 0,
        }

        resp = requests.post(f"{MOVIE_SERVICE_URL}/events", json=event)
        assert resp.status_code == 422  # Validation error

    def test_publish_missing_required_field(self):
        """Should reject event with missing required fields."""
        event = {
            "user_id": "test_user_004",
            # missing movie_id, event_type, etc.
        }

        resp = requests.post(f"{MOVIE_SERVICE_URL}/events", json=event)
        assert resp.status_code == 422

    def test_publish_all_event_types(self):
        """Should accept all valid event types."""
        session_id = str(uuid.uuid4())
        event_types = [
            "VIEW_STARTED", "VIEW_PAUSED", "VIEW_RESUMED",
            "VIEW_FINISHED", "LIKED", "SEARCHED",
        ]

        for et in event_types:
            event = {
                "user_id": "test_user_005",
                "movie_id": "test_movie_005",
                "event_type": et,
                "device_type": "TV",
                "session_id": session_id,
                "progress_seconds": 100,
            }
            resp = requests.post(f"{MOVIE_SERVICE_URL}/events", json=event)
            assert resp.status_code == 200, f"Failed for event_type={et}"


class TestFullPipeline:
    """Integration test: event → Kafka → ClickHouse."""

    def test_event_reaches_clickhouse(self):
        """
        Publish an event and verify it appears in ClickHouse.
        This tests the full pipeline: HTTP API → Kafka → ClickHouse Kafka Engine → MergeTree.
        """
        # Create a unique event
        event_id = str(uuid.uuid4())
        user_id = f"pipeline_test_{uuid.uuid4().hex[:8]}"
        event = {
            "event_id": event_id,
            "user_id": user_id,
            "movie_id": "pipeline_movie_001",
            "event_type": "VIEW_STARTED",
            "device_type": "DESKTOP",
            "session_id": str(uuid.uuid4()),
            "progress_seconds": 0,
        }

        # Publish event
        resp = requests.post(f"{MOVIE_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200

        # Wait for event to propagate through Kafka → ClickHouse
        # ClickHouse Kafka Engine polls periodically, so we need to wait
        time.sleep(5)

        ch_client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DB,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )

        max_wait = 60
        found = False
        for _ in range(max_wait):
            result = ch_client.query(
                "SELECT event_id, user_id, event_type FROM movie_events WHERE event_id = %(eid)s",
                parameters={"eid": event_id},
            )
            if result.result_rows:
                found = True
                row = result.result_rows[0]
                assert row[0] == event_id
                assert row[1] == user_id
                assert row[2] == "VIEW_STARTED"
                break
            time.sleep(1)

        ch_client.close()
        assert found, f"Event {event_id} not found in ClickHouse after {max_wait}s"

    def test_multiple_events_same_user(self):
        """Publish multiple events for the same user and verify ordering."""
        user_id = f"order_test_{uuid.uuid4().hex[:8]}"
        session_id = str(uuid.uuid4())
        events = [
            ("VIEW_STARTED", 0),
            ("VIEW_PAUSED", 600),
            ("VIEW_RESUMED", 600),
            ("VIEW_FINISHED", 3600),
        ]

        event_ids = []
        for event_type, progress in events:
            event = {
                "user_id": user_id,
                "movie_id": "order_movie_001",
                "event_type": event_type,
                "device_type": "TABLET",
                "session_id": session_id,
                "progress_seconds": progress,
            }
            resp = requests.post(f"{MOVIE_SERVICE_URL}/events", json=event)
            assert resp.status_code == 200
            event_ids.append(resp.json()["event_id"])

        # Wait and verify all events in ClickHouse
        time.sleep(5)

        ch_client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DB,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )

        max_wait = 60
        all_found = False
        for _ in range(max_wait):
            result = ch_client.query(
                """
                SELECT event_id, event_type, progress_seconds
                FROM movie_events
                WHERE user_id = %(uid)s AND session_id = %(sid)s
                ORDER BY timestamp
                """,
                parameters={"uid": user_id, "sid": session_id},
            )
            if len(result.result_rows) == len(events):
                all_found = True
                for i, row in enumerate(result.result_rows):
                    assert row[1] == events[i][0], f"Event {i}: expected {events[i][0]}, got {row[1]}"
                break
            time.sleep(1)

        ch_client.close()
        assert all_found, f"Not all events found in ClickHouse for user {user_id}"


class TestAggregation:
    """Test metrics aggregation."""

    def test_compute_metrics(self):
        """Trigger metrics computation and verify results."""
        # First, publish some events to ensure data exists
        session_id = str(uuid.uuid4())
        for i in range(5):
            event = {
                "user_id": f"agg_user_{i:03d}",
                "movie_id": f"agg_movie_{i % 3:03d}",
                "event_type": "VIEW_STARTED",
                "device_type": "DESKTOP",
                "session_id": session_id,
                "progress_seconds": 0,
            }
            requests.post(f"{MOVIE_SERVICE_URL}/events", json=event)

        # Wait for events to reach ClickHouse
        time.sleep(10)

        # Trigger computation
        resp = requests.post(f"{AGGREGATION_SERVICE_URL}/compute")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "metrics" in data

    def test_metrics_in_postgres(self):
        """Verify metrics are stored in PostgreSQL after computation."""
        # Trigger computation first
        resp = requests.post(f"{AGGREGATION_SERVICE_URL}/compute")
        assert resp.status_code == 200

        # Check PostgreSQL
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
        )
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM metrics")
                result = cur.fetchone()
                assert result["cnt"] > 0, "No metrics found in PostgreSQL"

                # Check DAU metric exists
                cur.execute("SELECT * FROM metrics WHERE metric_name = 'dau' LIMIT 1")
                dau = cur.fetchone()
                assert dau is not None, "DAU metric not found"
                assert dau["metric_value"] >= 0
        finally:
            conn.close()

    def test_idempotent_computation(self):
        """Running computation twice should not duplicate metrics."""
        # Run computation twice
        requests.post(f"{AGGREGATION_SERVICE_URL}/compute")
        requests.post(f"{AGGREGATION_SERVICE_URL}/compute")

        # Check no duplicates in PostgreSQL
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
        )
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT metric_date, metric_name, COUNT(*) as cnt
                    FROM metrics
                    GROUP BY metric_date, metric_name
                    HAVING COUNT(*) > 1
                """)
                duplicates = cur.fetchall()
                assert len(duplicates) == 0, f"Found duplicate metrics: {duplicates}"
        finally:
            conn.close()


class TestS3Export:
    """Test S3 export functionality."""

    def test_export_to_s3(self):
        """Export metrics to S3 and verify the file exists."""
        # Ensure metrics exist
        requests.post(f"{AGGREGATION_SERVICE_URL}/compute")

        # Trigger export
        resp = requests.post(f"{AGGREGATION_SERVICE_URL}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("success", "no_data")

        if data["status"] == "success":
            # Verify file in MinIO
            minio_client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=False,
            )

            target_date = data["date"]
            object_name = f"daily/{target_date}/aggregates.json"

            try:
                stat = minio_client.stat_object(MINIO_BUCKET, object_name)
                assert stat.size > 0, "Exported file is empty"

                # Download and verify content
                response = minio_client.get_object(MINIO_BUCKET, object_name)
                content = json.loads(response.read().decode("utf-8"))
                response.close()
                response.release_conn()

                assert "date" in content
                assert "metrics" in content
                assert content["date"] == target_date
                assert len(content["metrics"]) > 0
            except Exception as e:
                pytest.fail(f"Failed to verify S3 export: {e}")

    def test_export_overwrites(self):
        """Exporting twice should overwrite, not duplicate."""
        requests.post(f"{AGGREGATION_SERVICE_URL}/compute")

        # Export twice
        resp1 = requests.post(f"{AGGREGATION_SERVICE_URL}/export")
        resp2 = requests.post(f"{AGGREGATION_SERVICE_URL}/export")

        if resp1.status_code == 200 and resp2.status_code == 200:
            data1 = resp1.json()
            data2 = resp2.json()
            if data1["status"] == "success" and data2["status"] == "success":
                # Both should point to the same path
                assert data1["s3_path"] == data2["s3_path"]


class TestClickHouseSchema:
    """Test ClickHouse schema and tables."""

    def test_tables_exist(self):
        """Verify all required ClickHouse tables exist."""
        ch_client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DB,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )

        expected_tables = [
            "movie_events",
            "movie_events_kafka",
            "movie_events_mv",
            "daily_active_users",
            "daily_avg_view_duration",
            "daily_top_movies",
            "daily_view_conversion",
            "daily_retention",
            "daily_device_distribution",
        ]

        result = ch_client.query("SHOW TABLES")
        existing_tables = [row[0] for row in result.result_rows]

        for table in expected_tables:
            assert table in existing_tables, f"Table {table} not found in ClickHouse"

        ch_client.close()

    def test_movie_events_schema(self):
        """Verify movie_events table has correct columns."""
        ch_client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DB,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )

        result = ch_client.query("DESCRIBE TABLE movie_events")
        columns = {row[0]: row[1] for row in result.result_rows}

        assert "event_id" in columns
        assert "user_id" in columns
        assert "movie_id" in columns
        assert "event_type" in columns
        assert "timestamp" in columns
        assert "device_type" in columns
        assert "session_id" in columns
        assert "progress_seconds" in columns

        ch_client.close()
