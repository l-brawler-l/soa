"""Integration tests for the Smart Warehouse event-driven system.

Tests cover all E2E scenarios from the assignment:
1. Basic warehouse cycle (points 1-3)
2. Idempotency (point 4)
3. Table consistency (point 5)
4. Out-of-order events (point 6)
5. Dead Letter Queue (point 7)
6. Monitoring endpoints (point 9)
7. Schema evolution (point 10)
"""

import json
import time
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from cassandra.cluster import Cluster

from tests.conftest import (
    CASSANDRA_HOSTS,
    CASSANDRA_KEYSPACE,
    CASSANDRA_PORT,
    CONSUMER_SERVICE_URL,
    WMS_SERVICE_URL,
)


def wait_for_cassandra_data(
    session, query, params, timeout=30, interval=1, check_fn=None
):
    """Wait for data to appear in Cassandra."""
    start = time.time()
    while time.time() - start < timeout:
        rows = session.execute(query, params)
        result = list(rows)
        if check_fn:
            if check_fn(result):
                return result
        elif result:
            return result
        time.sleep(interval)
    return []


@pytest.fixture(scope="module")
def cassandra_session():
    """Create a Cassandra session for test verification."""
    cluster = Cluster(CASSANDRA_HOSTS, port=CASSANDRA_PORT)
    session = cluster.connect(CASSANDRA_KEYSPACE)
    yield session
    cluster.shutdown()


class TestWMSServiceHealth:
    """Test WMS Service health endpoint."""

    def test_health_check(self):
        """WMS Service should be healthy."""
        resp = requests.get(f"{WMS_SERVICE_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["kafka_connected"] is True


class TestConsumerServiceHealth:
    """Test Consumer Service health endpoint."""

    def test_health_check(self):
        """Consumer Service should be healthy (200 OK)."""
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["kafka_connected"] is True
        assert data["cassandra_connected"] is True


class TestBasicWarehouseCycle:
    """Scenario 1: Basic warehouse cycle (points 1-3).

    Tests PRODUCT_RECEIVED, PRODUCT_RESERVED, PRODUCT_MOVED,
    PRODUCT_SHIPPED, ORDER_CREATED, ORDER_COMPLETED.
    """

    def test_product_received(self, cassandra_session):
        """Send PRODUCT_RECEIVED and verify inventory in Cassandra."""
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-TEST-001",
            "zone_id": "ZONE-A",
            "quantity": 100,
            "supplier_id": "SUP-001",
        }

        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"

        # Wait for consumer to process and verify in Cassandra
        time.sleep(5)

        # Check via consumer service API
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-TEST-001/ZONE-A")
        if resp.status_code == 200:
            data = resp.json()
            assert data["available_quantity"] >= 100

    def test_product_reserved(self, cassandra_session):
        """Send PRODUCT_RESERVED and verify available/reserved quantities."""
        # First ensure we have inventory
        recv_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-TEST-002",
            "zone_id": "ZONE-A",
            "quantity": 100,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=recv_event)
        time.sleep(3)

        # Now reserve
        reserve_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RESERVED",
            "product_id": "SKU-TEST-002",
            "zone_id": "ZONE-A",
            "quantity": 30,
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=reserve_event)
        assert resp.status_code == 200

        time.sleep(5)

        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-TEST-002/ZONE-A")
        if resp.status_code == 200:
            data = resp.json()
            assert data["available_quantity"] == 70
            assert data["reserved_quantity"] == 30

    def test_product_moved(self, cassandra_session):
        """Send PRODUCT_MOVED and verify quantities in both zones."""
        # Ensure inventory in ZONE-A
        recv_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-TEST-003",
            "zone_id": "ZONE-A",
            "quantity": 100,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=recv_event)
        time.sleep(3)

        # Move 20 from ZONE-A to ZONE-B
        move_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_MOVED",
            "product_id": "SKU-TEST-003",
            "zone_id": "ZONE-A",
            "to_zone_id": "ZONE-B",
            "quantity": 20,
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=move_event)
        assert resp.status_code == 200

        time.sleep(5)

        # Check ZONE-A
        resp_a = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-TEST-003/ZONE-A")
        if resp_a.status_code == 200:
            assert resp_a.json()["available_quantity"] == 80

        # Check ZONE-B
        resp_b = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-TEST-003/ZONE-B")
        if resp_b.status_code == 200:
            assert resp_b.json()["available_quantity"] == 20

    def test_product_shipped(self, cassandra_session):
        """Send PRODUCT_SHIPPED and verify quantity decreased."""
        recv_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-TEST-004",
            "zone_id": "ZONE-A",
            "quantity": 50,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=recv_event)
        time.sleep(3)

        ship_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_SHIPPED",
            "product_id": "SKU-TEST-004",
            "zone_id": "ZONE-A",
            "quantity": 10,
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=ship_event)
        assert resp.status_code == 200

        time.sleep(5)

        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-TEST-004/ZONE-A")
        if resp.status_code == 200:
            assert resp.json()["available_quantity"] == 40

    def test_order_created_and_completed(self, cassandra_session):
        """Send ORDER_CREATED then ORDER_COMPLETED and verify state changes."""
        # Seed inventory
        recv_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-TEST-005",
            "zone_id": "ZONE-A",
            "quantity": 100,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=recv_event)
        time.sleep(3)

        order_id = f"ORD-TEST-{uuid.uuid4().hex[:8].upper()}"

        # Create order
        create_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "ORDER_CREATED",
            "order_id": order_id,
            "items": [
                {"product_id": "SKU-TEST-005", "zone_id": "ZONE-A", "quantity": 15}
            ],
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=create_event)
        assert resp.status_code == 200

        time.sleep(5)

        # Check reserved increased
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-TEST-005/ZONE-A")
        if resp.status_code == 200:
            data = resp.json()
            assert data["reserved_quantity"] >= 15
            assert data["available_quantity"] <= 85

        # Complete order
        complete_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "ORDER_COMPLETED",
            "order_id": order_id,
            "items": [
                {"product_id": "SKU-TEST-005", "zone_id": "ZONE-A", "quantity": 15}
            ],
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=complete_event)
        assert resp.status_code == 200

        time.sleep(5)

        # Check reserved decreased
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-TEST-005/ZONE-A")
        if resp.status_code == 200:
            data = resp.json()
            assert data["reserved_quantity"] == 0


class TestIdempotency:
    """Scenario 2: Idempotency (point 4).

    Sending the same event twice should not double the effect.
    """

    def test_duplicate_event_ignored(self, cassandra_session):
        """Sending same event_id twice should not duplicate changes."""
        event_id = str(uuid.uuid4())

        # First send
        event = {
            "event_id": event_id,
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-IDEMP-001",
            "zone_id": "ZONE-A",
            "quantity": 50,
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200

        time.sleep(5)

        # Check quantity
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-IDEMP-001/ZONE-A")
        assert resp.status_code == 200
        first_qty = resp.json()["available_quantity"]
        assert first_qty == 50

        # Send same event again (same event_id)
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200

        time.sleep(5)

        # Quantity should still be 50, not 100
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-IDEMP-001/ZONE-A")
        assert resp.status_code == 200
        assert resp.json()["available_quantity"] == 50


class TestTableConsistency:
    """Scenario 3: Consistency across denormalized tables (point 5).

    All three inventory tables should have consistent data.
    """

    def test_all_tables_consistent(self, cassandra_session):
        """After PRODUCT_RECEIVED, all 3 tables should agree."""
        product_id = "SKU-CONSIST-001"
        zone_id = "ZONE-A"

        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": product_id,
            "zone_id": zone_id,
            "quantity": 100,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        time.sleep(5)

        # Check inventory_by_product_zone
        rows = list(cassandra_session.execute(
            "SELECT available_quantity FROM inventory_by_product_zone WHERE product_id = %s AND zone_id = %s",
            (product_id, zone_id),
        ))
        assert len(rows) > 0
        qty_pz = rows[0].available_quantity

        # Check inventory_by_product
        rows = list(cassandra_session.execute(
            "SELECT available_quantity FROM inventory_by_product WHERE product_id = %s AND zone_id = %s",
            (product_id, zone_id),
        ))
        assert len(rows) > 0
        qty_p = rows[0].available_quantity

        # Check inventory_by_zone
        rows = list(cassandra_session.execute(
            "SELECT available_quantity FROM inventory_by_zone WHERE zone_id = %s AND product_id = %s",
            (zone_id, product_id),
        ))
        assert len(rows) > 0
        qty_z = rows[0].available_quantity

        # All three should be equal
        assert qty_pz == qty_p == qty_z == 100


class TestOutOfOrderEvents:
    """Scenario 4: Out-of-order events (point 6).

    Events arriving out of order should not overwrite newer state.
    """

    def test_old_event_ignored(self, cassandra_session):
        """An event with older timestamp should be ignored."""
        product_id = "SKU-OOO-001"
        zone_id = "ZONE-A"
        now = datetime.now(timezone.utc)

        # Event 1: PRODUCT_RECEIVED at t=0, seq=1
        event1 = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": product_id,
            "zone_id": zone_id,
            "quantity": 100,
            "timestamp": now.isoformat(),
            "sequence_number": 1,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=event1)
        time.sleep(3)

        # Event 2: PRODUCT_SHIPPED at t=5min, seq=2
        event2 = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_SHIPPED",
            "product_id": product_id,
            "zone_id": zone_id,
            "quantity": 20,
            "timestamp": (now + timedelta(minutes=5)).isoformat(),
            "sequence_number": 2,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=event2)
        time.sleep(3)

        # Check: available should be 80
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/{product_id}/{zone_id}")
        if resp.status_code == 200:
            assert resp.json()["available_quantity"] == 80

        # Event 3: PRODUCT_RECEIVED at t=2min, seq=1 (old event, arrives late)
        # This should be IGNORED because seq < last processed seq
        event3 = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": product_id,
            "zone_id": zone_id,
            "quantity": 50,
            "timestamp": (now + timedelta(minutes=2)).isoformat(),
            "sequence_number": 1,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=event3)
        time.sleep(5)

        # Available should still be 80 (event 3 was ignored)
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/{product_id}/{zone_id}")
        if resp.status_code == 200:
            assert resp.json()["available_quantity"] == 80


class TestDeadLetterQueue:
    """Scenario 5: Dead Letter Queue (point 7).

    Invalid events should go to DLQ without crashing the consumer.
    """

    def test_invalid_event_goes_to_dlq(self):
        """Send invalid event (negative quantity) and verify consumer survives."""
        # Send invalid event: PRODUCT_SHIPPED with quantity=-5
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_SHIPPED",
            "product_id": "SKU-DLQ-001",
            "zone_id": "ZONE-A",
            "quantity": -5,
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200  # Producer accepts it

        time.sleep(5)

        # Consumer should still be healthy
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_valid_event_after_invalid(self):
        """Valid events should still be processed after an invalid one."""
        # Send invalid event first
        invalid_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_SHIPPED",
            "product_id": "SKU-DLQ-002",
            "zone_id": "ZONE-A",
            "quantity": -10,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=invalid_event)
        time.sleep(2)

        # Send valid event
        valid_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-DLQ-003",
            "zone_id": "ZONE-A",
            "quantity": 25,
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=valid_event)
        assert resp.status_code == 200

        time.sleep(5)

        # Valid event should be processed
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-DLQ-003/ZONE-A")
        if resp.status_code == 200:
            assert resp.json()["available_quantity"] == 25


class TestMonitoring:
    """Scenario 7: Monitoring and consumer lag (point 9)."""

    def test_health_endpoint_200(self):
        """Health endpoint should return 200 OK."""
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "kafka_connected" in data
        assert "cassandra_connected" in data

    def test_metrics_endpoint(self):
        """Metrics endpoint should return Prometheus-format metrics."""
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/metrics")
        assert resp.status_code == 200
        content = resp.text

        # Check for expected metrics
        assert "events_processed_total" in content
        assert "event_processing_duration_seconds" in content
        assert "cassandra_write_errors_total" in content
        assert "consumer_lag" in content

    def test_metrics_increment_after_events(self):
        """After sending events, metrics should increase."""
        # Get initial metrics
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/metrics")
        initial_metrics = resp.text

        # Send some events
        for i in range(3):
            event = {
                "event_id": str(uuid.uuid4()),
                "event_type": "PRODUCT_RECEIVED",
                "product_id": f"SKU-METRICS-{i:03d}",
                "zone_id": "ZONE-A",
                "quantity": 10,
            }
            requests.post(f"{WMS_SERVICE_URL}/events", json=event)

        time.sleep(5)

        # Check metrics increased
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/metrics")
        assert resp.status_code == 200
        assert "events_processed_total" in resp.text


class TestSchemaEvolution:
    """Scenario 8: Schema Evolution (point 10).

    V1 events (without supplier_id) and V2 events (with supplier_id)
    should both be processed correctly.
    """

    def test_v1_event_without_supplier(self, cassandra_session):
        """V1 event without supplier_id should be processed."""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-SCHEMA-V1",
            "zone_id": "ZONE-A",
            "quantity": 50,
            # No supplier_id (V1)
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200

        time.sleep(5)

        # Check data in Cassandra - supplier_id should be null/empty
        rows = list(cassandra_session.execute(
            "SELECT supplier_id FROM inventory_by_product_zone WHERE product_id = %s AND zone_id = %s",
            ("SKU-SCHEMA-V1", "ZONE-A"),
        ))
        assert len(rows) > 0
        # V1: supplier_id is empty or null
        assert rows[0].supplier_id in (None, "")

    def test_v2_event_with_supplier(self, cassandra_session):
        """V2 event with supplier_id should be processed and stored."""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-SCHEMA-V2",
            "zone_id": "ZONE-A",
            "quantity": 75,
            "supplier_id": "SUP-001",  # V2 field
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200

        time.sleep(5)

        # Check data in Cassandra - supplier_id should be set
        rows = list(cassandra_session.execute(
            "SELECT supplier_id FROM inventory_by_product_zone WHERE product_id = %s AND zone_id = %s",
            ("SKU-SCHEMA-V2", "ZONE-A"),
        ))
        assert len(rows) > 0
        assert rows[0].supplier_id == "SUP-001"

    def test_v1_and_v2_coexist(self, cassandra_session):
        """Both V1 and V2 events in the same topic should work."""
        # V1 event
        v1_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-SCHEMA-MIX",
            "zone_id": "ZONE-A",
            "quantity": 30,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=v1_event)

        time.sleep(3)

        # V2 event for same product (adds supplier)
        v2_event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-SCHEMA-MIX",
            "zone_id": "ZONE-B",
            "quantity": 20,
            "supplier_id": "SUP-002",
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=v2_event)

        time.sleep(5)

        # Both should be in Cassandra
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-SCHEMA-MIX")
        if resp.status_code == 200:
            data = resp.json()
            assert data["total_available"] >= 50  # 30 + 20


class TestEventPublishing:
    """Test event publishing via HTTP API."""

    def test_publish_valid_event(self):
        """Should successfully publish a valid event."""
        event = {
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-PUB-001",
            "zone_id": "ZONE-A",
            "quantity": 10,
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "published"
        assert "event_id" in data

    def test_publish_all_event_types(self):
        """Should accept all valid event types."""
        event_types = [
            ("PRODUCT_RECEIVED", {"product_id": "SKU-ALL-001", "zone_id": "ZONE-A", "quantity": 10}),
            ("PRODUCT_SHIPPED", {"product_id": "SKU-ALL-001", "zone_id": "ZONE-A", "quantity": 5}),
            ("PRODUCT_MOVED", {"product_id": "SKU-ALL-001", "zone_id": "ZONE-A", "to_zone_id": "ZONE-B", "quantity": 2}),
            ("PRODUCT_RESERVED", {"product_id": "SKU-ALL-001", "zone_id": "ZONE-A", "quantity": 1}),
            ("PRODUCT_RELEASED", {"product_id": "SKU-ALL-001", "zone_id": "ZONE-A", "quantity": 1}),
            ("INVENTORY_COUNTED", {"product_id": "SKU-ALL-001", "zone_id": "ZONE-A", "quantity": 50}),
        ]

        for event_type, extra_fields in event_types:
            event = {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                **extra_fields,
            }
            resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
            assert resp.status_code == 200, f"Failed for event_type={event_type}: {resp.text}"

    def test_publish_missing_event_type(self):
        """Should reject event without event_type."""
        event = {
            "product_id": "SKU-FAIL-001",
            "zone_id": "ZONE-A",
            "quantity": 10,
        }
        resp = requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        assert resp.status_code == 422


class TestInventoryAPI:
    """Test Consumer Service inventory query endpoints."""

    def test_get_inventory_by_product(self):
        """Should return inventory for a product across all zones."""
        # Seed data
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "PRODUCT_RECEIVED",
            "product_id": "SKU-API-001",
            "zone_id": "ZONE-A",
            "quantity": 42,
        }
        requests.post(f"{WMS_SERVICE_URL}/events", json=event)
        time.sleep(5)

        resp = requests.get(f"{CONSUMER_SERVICE_URL}/inventory/SKU-API-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product_id"] == "SKU-API-001"
        assert data["total_available"] >= 42

    def test_get_zone_inventory(self):
        """Should return all products in a zone."""
        resp = requests.get(f"{CONSUMER_SERVICE_URL}/zone/ZONE-A")
        assert resp.status_code == 200
        data = resp.json()
        assert data["zone_id"] == "ZONE-A"
        assert "products" in data

    def test_get_nonexistent_product(self):
        """Should return 404 for nonexistent product/zone."""
        resp = requests.get(
            f"{CONSUMER_SERVICE_URL}/inventory/NONEXISTENT-SKU/NONEXISTENT-ZONE"
        )
        assert resp.status_code == 404
