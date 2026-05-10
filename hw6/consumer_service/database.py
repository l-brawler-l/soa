"""Cassandra database client with migration support.

Data model design rationale:
- Tables are designed for query patterns (Cassandra best practice)
- Denormalized tables for different access patterns
- Logged batches ensure consistency across denormalized tables
- TTL on processed_events for automatic cleanup

Tables:
1. inventory_by_product_zone: Get inventory for a specific product in a specific zone
   - PK: (product_id, zone_id) - allows querying by product+zone
2. inventory_by_product: Get total inventory for a product across all zones
   - PK: (product_id), CK: (zone_id) - allows querying all zones for a product
3. inventory_by_zone: Get all products in a zone
   - PK: (zone_id), CK: (product_id) - allows querying all products in a zone
4. orders: Track order status
   - PK: (order_id)
5. event_log: Audit trail of all events
   - PK: (product_id), CK: (timestamp DESC, event_id) - time-ordered per product
6. processed_events: Idempotency tracking
   - PK: (event_id) with TTL
7. entity_timestamps: Track last processed timestamp per entity for out-of-order handling
   - PK: (entity_key)
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster, Session
from cassandra.policies import (
    DCAwareRoundRobinPolicy,
    RetryPolicy,
    TokenAwarePolicy,
)
from cassandra.query import BatchStatement, SimpleStatement

from consumer_service.config import Config

logger = logging.getLogger(__name__)

CL_MAP = {
    "ONE": ConsistencyLevel.ONE,
    "QUORUM": ConsistencyLevel.QUORUM,
    "ALL": ConsistencyLevel.ALL,
    "LOCAL_QUORUM": ConsistencyLevel.LOCAL_QUORUM,
}


class CassandraClient:
    """Cassandra client with connection management and migration support."""

    def __init__(self, config: Config):
        self.config = config
        self._cluster: Optional[Cluster] = None
        self._session: Optional[Session] = None
        self._write_cl = CL_MAP.get(config.CASSANDRA_WRITE_CL, ConsistencyLevel.QUORUM)
        self._read_cl = CL_MAP.get(config.CASSANDRA_READ_CL, ConsistencyLevel.ONE)

    def connect(self) -> None:
        """Connect to Cassandra with retries."""
        max_retries = 30
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                self._cluster = Cluster(
                    contact_points=self.config.CASSANDRA_HOSTS,
                    port=self.config.CASSANDRA_PORT,
                    load_balancing_policy=TokenAwarePolicy(
                        DCAwareRoundRobinPolicy(local_dc="datacenter1")
                    ),
                    protocol_version=4,
                )
                self._session = self._cluster.connect()
                logger.info(
                    "Connected to Cassandra at %s:%s",
                    self.config.CASSANDRA_HOSTS,
                    self.config.CASSANDRA_PORT,
                )
                return
            except Exception as e:
                logger.warning(
                    "Failed to connect to Cassandra (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 15)

        raise ConnectionError("Failed to connect to Cassandra after retries")

    @property
    def is_connected(self) -> bool:
        return self._session is not None and not self._session.is_shutdown

    def run_migrations(self) -> None:
        """Create keyspace and tables (Cassandra migration)."""
        if not self._session:
            raise RuntimeError("Not connected to Cassandra")

        rf = self.config.CASSANDRA_REPLICATION_FACTOR
        ks = self.config.CASSANDRA_KEYSPACE

        logger.info("Running Cassandra migrations...")

        # Create keyspace with NetworkTopologyStrategy
        self._session.execute(f"""
            CREATE KEYSPACE IF NOT EXISTS {ks}
            WITH replication = {{
                'class': 'NetworkTopologyStrategy',
                'datacenter1': {rf}
            }}
        """)

        self._session.set_keyspace(ks)

        # Table 1: inventory_by_product_zone
        # Query: SELECT * FROM inventory_by_product_zone WHERE product_id = ? AND zone_id = ?
        self._session.execute(f"""
            CREATE TABLE IF NOT EXISTS {ks}.inventory_by_product_zone (
                product_id text,
                zone_id text,
                available_quantity int,
                reserved_quantity int,
                last_updated timestamp,
                last_sequence bigint,
                supplier_id text,
                PRIMARY KEY (product_id, zone_id)
            )
        """)

        # Table 2: inventory_by_product
        # Query: SELECT * FROM inventory_by_product WHERE product_id = ?
        # Shows all zones for a product
        self._session.execute(f"""
            CREATE TABLE IF NOT EXISTS {ks}.inventory_by_product (
                product_id text,
                zone_id text,
                available_quantity int,
                reserved_quantity int,
                last_updated timestamp,
                supplier_id text,
                PRIMARY KEY (product_id, zone_id)
            )
        """)

        # Table 3: inventory_by_zone
        # Query: SELECT * FROM inventory_by_zone WHERE zone_id = ?
        # Shows all products in a zone
        self._session.execute(f"""
            CREATE TABLE IF NOT EXISTS {ks}.inventory_by_zone (
                zone_id text,
                product_id text,
                available_quantity int,
                reserved_quantity int,
                last_updated timestamp,
                supplier_id text,
                PRIMARY KEY (zone_id, product_id)
            )
        """)

        # Table 4: orders
        self._session.execute(f"""
            CREATE TABLE IF NOT EXISTS {ks}.orders (
                order_id text,
                status text,
                items text,
                created_at timestamp,
                completed_at timestamp,
                PRIMARY KEY (order_id)
            )
        """)

        # Table 5: event_log (audit trail)
        self._session.execute(f"""
            CREATE TABLE IF NOT EXISTS {ks}.event_log (
                product_id text,
                event_timestamp timestamp,
                event_id text,
                event_type text,
                zone_id text,
                quantity int,
                details text,
                PRIMARY KEY (product_id, event_timestamp, event_id)
            ) WITH CLUSTERING ORDER BY (event_timestamp DESC, event_id ASC)
        """)

        # Table 6: processed_events (idempotency)
        self._session.execute(f"""
            CREATE TABLE IF NOT EXISTS {ks}.processed_events (
                event_id text,
                processed_at timestamp,
                PRIMARY KEY (event_id)
            ) WITH default_time_to_live = 604800
        """)
        # TTL = 7 days (604800 seconds) for automatic cleanup

        # Table 7: entity_timestamps (out-of-order handling)
        self._session.execute(f"""
            CREATE TABLE IF NOT EXISTS {ks}.entity_timestamps (
                entity_key text,
                last_timestamp timestamp,
                last_sequence bigint,
                PRIMARY KEY (entity_key)
            )
        """)

        # Schema evolution: add supplier_id column if not exists
        # This is safe to run multiple times (IF NOT EXISTS)
        try:
            self._session.execute(f"""
                ALTER TABLE {ks}.inventory_by_product_zone ADD supplier_id text
            """)
        except Exception:
            pass  # Column already exists

        try:
            self._session.execute(f"""
                ALTER TABLE {ks}.inventory_by_product ADD supplier_id text
            """)
        except Exception:
            pass

        try:
            self._session.execute(f"""
                ALTER TABLE {ks}.inventory_by_zone ADD supplier_id text
            """)
        except Exception:
            pass

        logger.info("Cassandra migrations completed successfully")

    def is_event_processed(self, event_id: str) -> bool:
        """Check if an event has already been processed (idempotency)."""
        ks = self.config.CASSANDRA_KEYSPACE
        stmt = SimpleStatement(
            f"SELECT event_id FROM {ks}.processed_events WHERE event_id = %s",
            consistency_level=self._read_cl,
        )
        result = self._session.execute(stmt, (event_id,))
        return result.one() is not None

    def mark_event_processed(self, event_id: str, processed_at: datetime) -> SimpleStatement:
        """Return a statement to mark an event as processed."""
        ks = self.config.CASSANDRA_KEYSPACE
        return SimpleStatement(
            f"INSERT INTO {ks}.processed_events (event_id, processed_at) VALUES (%s, %s)",
            consistency_level=self._write_cl,
        ), (event_id, processed_at)

    def check_timestamp_order(
        self, entity_key: str, event_timestamp: datetime, sequence_number: int
    ) -> bool:
        """
        Check if this event is newer than the last processed event for this entity.
        Returns True if the event should be processed, False if it should be skipped.
        """
        ks = self.config.CASSANDRA_KEYSPACE
        stmt = SimpleStatement(
            f"SELECT last_timestamp, last_sequence FROM {ks}.entity_timestamps WHERE entity_key = %s",
            consistency_level=self._read_cl,
        )
        result = self._session.execute(stmt, (entity_key,))
        row = result.one()

        if row is None:
            return True

        last_ts = row.last_timestamp
        last_seq = row.last_sequence

        # Compare by sequence number first, then by timestamp
        if sequence_number > 0 and last_seq and last_seq > 0:
            return sequence_number > last_seq

        if last_ts and event_timestamp:
            return event_timestamp > last_ts

        return True

    def update_entity_timestamp(
        self, entity_key: str, event_timestamp: datetime, sequence_number: int
    ) -> Tuple[SimpleStatement, tuple]:
        """Return a statement to update the entity timestamp."""
        ks = self.config.CASSANDRA_KEYSPACE
        return (
            SimpleStatement(
                f"INSERT INTO {ks}.entity_timestamps (entity_key, last_timestamp, last_sequence) VALUES (%s, %s, %s)",
                consistency_level=self._write_cl,
            ),
            (entity_key, event_timestamp, sequence_number),
        )

    def execute_batch(self, statements: List[Tuple[SimpleStatement, tuple]]) -> None:
        """Execute a logged batch of statements for atomic updates."""
        if not statements:
            return

        batch = BatchStatement(consistency_level=self._write_cl)
        for stmt, params in statements:
            batch.add(stmt, params)

        self._session.execute(batch)

    def get_inventory_by_product_zone(
        self, product_id: str, zone_id: str
    ) -> Optional[Dict]:
        """Get inventory for a specific product in a specific zone."""
        ks = self.config.CASSANDRA_KEYSPACE
        stmt = SimpleStatement(
            f"SELECT * FROM {ks}.inventory_by_product_zone WHERE product_id = %s AND zone_id = %s",
            consistency_level=self._read_cl,
        )
        result = self._session.execute(stmt, (product_id, zone_id))
        row = result.one()
        if row:
            return {
                "product_id": row.product_id,
                "zone_id": row.zone_id,
                "available_quantity": row.available_quantity or 0,
                "reserved_quantity": row.reserved_quantity or 0,
                "last_updated": row.last_updated,
                "supplier_id": getattr(row, "supplier_id", None),
            }
        return None

    def get_inventory_by_product(self, product_id: str) -> List[Dict]:
        """Get all inventory for a product across all zones."""
        ks = self.config.CASSANDRA_KEYSPACE
        stmt = SimpleStatement(
            f"SELECT * FROM {ks}.inventory_by_product WHERE product_id = %s",
            consistency_level=self._read_cl,
        )
        result = self._session.execute(stmt, (product_id,))
        return [
            {
                "product_id": row.product_id,
                "zone_id": row.zone_id,
                "available_quantity": row.available_quantity or 0,
                "reserved_quantity": row.reserved_quantity or 0,
                "last_updated": row.last_updated,
                "supplier_id": getattr(row, "supplier_id", None),
            }
            for row in result
        ]

    def get_inventory_by_zone(self, zone_id: str) -> List[Dict]:
        """Get all products in a zone."""
        ks = self.config.CASSANDRA_KEYSPACE
        stmt = SimpleStatement(
            f"SELECT * FROM {ks}.inventory_by_zone WHERE zone_id = %s",
            consistency_level=self._read_cl,
        )
        result = self._session.execute(stmt, (zone_id,))
        return [
            {
                "zone_id": row.zone_id,
                "product_id": row.product_id,
                "available_quantity": row.available_quantity or 0,
                "reserved_quantity": row.reserved_quantity or 0,
                "last_updated": row.last_updated,
                "supplier_id": getattr(row, "supplier_id", None),
            }
            for row in result
        ]

    def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order by ID."""
        ks = self.config.CASSANDRA_KEYSPACE
        stmt = SimpleStatement(
            f"SELECT * FROM {ks}.orders WHERE order_id = %s",
            consistency_level=self._read_cl,
        )
        result = self._session.execute(stmt, (order_id,))
        row = result.one()
        if row:
            return {
                "order_id": row.order_id,
                "status": row.status,
                "items": row.items,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
        return None

    def build_inventory_update_statements(
        self,
        product_id: str,
        zone_id: str,
        available_delta: int,
        reserved_delta: int,
        event_timestamp: datetime,
        supplier_id: str = "",
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """
        Build statements to update all 3 inventory tables atomically.
        Uses counter-like logic: reads current values, computes new values, writes.
        """
        ks = self.config.CASSANDRA_KEYSPACE
        statements = []

        # Read current values
        current = self.get_inventory_by_product_zone(product_id, zone_id)
        current_available = current["available_quantity"] if current else 0
        current_reserved = current["reserved_quantity"] if current else 0
        current_supplier = (current.get("supplier_id") or "") if current else ""

        new_available = current_available + available_delta
        new_reserved = current_reserved + reserved_delta
        new_supplier = supplier_id if supplier_id else current_supplier

        # Update inventory_by_product_zone
        stmt1 = SimpleStatement(
            f"""UPDATE {ks}.inventory_by_product_zone
                SET available_quantity = %s, reserved_quantity = %s,
                    last_updated = %s, supplier_id = %s
                WHERE product_id = %s AND zone_id = %s""",
            consistency_level=self._write_cl,
        )
        statements.append((stmt1, (new_available, new_reserved, event_timestamp, new_supplier, product_id, zone_id)))

        # Update inventory_by_product
        stmt2 = SimpleStatement(
            f"""UPDATE {ks}.inventory_by_product
                SET available_quantity = %s, reserved_quantity = %s,
                    last_updated = %s, supplier_id = %s
                WHERE product_id = %s AND zone_id = %s""",
            consistency_level=self._write_cl,
        )
        statements.append((stmt2, (new_available, new_reserved, event_timestamp, new_supplier, product_id, zone_id)))

        # Update inventory_by_zone
        stmt3 = SimpleStatement(
            f"""UPDATE {ks}.inventory_by_zone
                SET available_quantity = %s, reserved_quantity = %s,
                    last_updated = %s, supplier_id = %s
                WHERE zone_id = %s AND product_id = %s""",
            consistency_level=self._write_cl,
        )
        statements.append((stmt3, (new_available, new_reserved, event_timestamp, new_supplier, zone_id, product_id)))

        return statements

    def build_inventory_set_statements(
        self,
        product_id: str,
        zone_id: str,
        available_quantity: int,
        reserved_quantity: int,
        event_timestamp: datetime,
        supplier_id: str = "",
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """Build statements to SET (not delta) inventory values across all 3 tables."""
        ks = self.config.CASSANDRA_KEYSPACE
        statements = []

        stmt1 = SimpleStatement(
            f"""UPDATE {ks}.inventory_by_product_zone
                SET available_quantity = %s, reserved_quantity = %s,
                    last_updated = %s, supplier_id = %s
                WHERE product_id = %s AND zone_id = %s""",
            consistency_level=self._write_cl,
        )
        statements.append((stmt1, (available_quantity, reserved_quantity, event_timestamp, supplier_id, product_id, zone_id)))

        stmt2 = SimpleStatement(
            f"""UPDATE {ks}.inventory_by_product
                SET available_quantity = %s, reserved_quantity = %s,
                    last_updated = %s, supplier_id = %s
                WHERE product_id = %s AND zone_id = %s""",
            consistency_level=self._write_cl,
        )
        statements.append((stmt2, (available_quantity, reserved_quantity, event_timestamp, supplier_id, product_id, zone_id)))

        stmt3 = SimpleStatement(
            f"""UPDATE {ks}.inventory_by_zone
                SET available_quantity = %s, reserved_quantity = %s,
                    last_updated = %s, supplier_id = %s
                WHERE zone_id = %s AND product_id = %s""",
            consistency_level=self._write_cl,
        )
        statements.append((stmt3, (available_quantity, reserved_quantity, event_timestamp, supplier_id, zone_id, product_id)))

        return statements

    def build_event_log_statement(
        self,
        product_id: str,
        event_timestamp: datetime,
        event_id: str,
        event_type: str,
        zone_id: str,
        quantity: int,
        details: str = "",
    ) -> Tuple[SimpleStatement, tuple]:
        """Build statement to insert into event_log."""
        ks = self.config.CASSANDRA_KEYSPACE
        stmt = SimpleStatement(
            f"""INSERT INTO {ks}.event_log
                (product_id, event_timestamp, event_id, event_type, zone_id, quantity, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            consistency_level=self._write_cl,
        )
        return stmt, (product_id, event_timestamp, event_id, event_type, zone_id, quantity, details)

    def build_order_statement(
        self,
        order_id: str,
        status: str,
        items: str,
        created_at: datetime,
        completed_at: Optional[datetime] = None,
    ) -> Tuple[SimpleStatement, tuple]:
        """Build statement to insert/update an order."""
        ks = self.config.CASSANDRA_KEYSPACE
        stmt = SimpleStatement(
            f"""INSERT INTO {ks}.orders
                (order_id, status, items, created_at, completed_at)
                VALUES (%s, %s, %s, %s, %s)""",
            consistency_level=self._write_cl,
        )
        return stmt, (order_id, status, items, created_at, completed_at)

    def close(self) -> None:
        """Close the connection."""
        if self._cluster:
            self._cluster.shutdown()
            logger.info("Cassandra connection closed")
