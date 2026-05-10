"""Event handler - processes warehouse events and updates Cassandra state.

Implements:
- Idempotent processing (event_id dedup)
- Consistent batch updates across denormalized tables
- Out-of-order event handling (timestamp/sequence-based)
- All event types from the warehouse domain
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from cassandra.query import SimpleStatement

from consumer_service.database import CassandraClient

logger = logging.getLogger(__name__)

# Protobuf event type enum to string mapping
EVENT_TYPE_NAMES = {
    0: "EVENT_TYPE_UNSPECIFIED",
    1: "PRODUCT_RECEIVED",
    2: "PRODUCT_SHIPPED",
    3: "PRODUCT_MOVED",
    4: "PRODUCT_RESERVED",
    5: "PRODUCT_RELEASED",
    6: "INVENTORY_COUNTED",
    7: "ORDER_CREATED",
    8: "ORDER_COMPLETED",
}


class EventValidationError(Exception):
    """Raised when event validation fails."""
    pass


class EventHandler:
    """Handles warehouse events and updates Cassandra state."""

    def __init__(self, db: CassandraClient):
        self.db = db

    def process_event(self, event) -> None:
        """
        Process a single warehouse event.

        Steps:
        1. Validate the event
        2. Check idempotency (skip if already processed)
        3. Check timestamp ordering (skip if out-of-order)
        4. Build batch statements for all denormalized tables
        5. Execute batch atomically
        6. Commit offset after successful processing

        Args:
            event: Parsed protobuf WarehouseEvent message

        Raises:
            EventValidationError: If event fails validation
            Exception: For unexpected errors (will be sent to DLQ)
        """
        event_id = event.event_id
        event_type_num = event.event_type
        event_type = EVENT_TYPE_NAMES.get(event_type_num, "UNKNOWN")
        event_timestamp = event.timestamp.ToDatetime().replace(tzinfo=timezone.utc)
        sequence_number = event.sequence_number

        logger.info(
            "Processing event: event_id=%s, event_type=%s, sequence=%d",
            event_id, event_type, sequence_number,
        )

        # Step 1: Validate
        self._validate_event(event, event_type)

        # Step 2: Idempotency check
        if self.db.is_event_processed(event_id):
            logger.info("Event %s already processed, skipping (idempotent)", event_id)
            return

        # Step 3: Out-of-order check
        entity_key = self._get_entity_key(event, event_type)
        if entity_key and not self.db.check_timestamp_order(
            entity_key, event_timestamp, sequence_number
        ):
            logger.info(
                "Event %s is out-of-order (entity=%s, ts=%s, seq=%d), skipping",
                event_id, entity_key, event_timestamp, sequence_number,
            )
            return

        # Step 4: Build batch statements
        statements = []

        # Mark event as processed
        mark_stmt, mark_params = self.db.mark_event_processed(event_id, datetime.now(timezone.utc))
        statements.append((mark_stmt, mark_params))

        # Update entity timestamp
        if entity_key:
            ts_stmt, ts_params = self.db.update_entity_timestamp(
                entity_key, event_timestamp, sequence_number
            )
            statements.append((ts_stmt, ts_params))

        # Process by event type
        handler_method = getattr(self, f"_handle_{event_type.lower()}", None)
        if handler_method is None:
            raise EventValidationError(f"Unknown event type: {event_type}")

        event_statements = handler_method(event, event_type, event_timestamp)
        statements.extend(event_statements)

        # Step 5: Execute batch atomically
        self.db.execute_batch(statements)

        logger.info(
            "Event %s (%s) processed successfully with %d statements",
            event_id, event_type, len(statements),
        )

    def _validate_event(self, event, event_type: str) -> None:
        """Validate event fields."""
        if not event.event_id:
            raise EventValidationError("Missing event_id")

        if event_type == "EVENT_TYPE_UNSPECIFIED" or event_type == "UNKNOWN":
            raise EventValidationError(f"Invalid event type: {event.event_type}")

        if event_type in ("PRODUCT_RECEIVED", "PRODUCT_SHIPPED", "PRODUCT_RESERVED",
                          "PRODUCT_RELEASED", "INVENTORY_COUNTED"):
            if not event.product_id:
                raise EventValidationError(f"Missing product_id for {event_type}")
            if not event.zone_id:
                raise EventValidationError(f"Missing zone_id for {event_type}")
            if event_type != "INVENTORY_COUNTED" and event.quantity <= 0:
                raise EventValidationError(
                    f"Invalid quantity: {event.quantity} (must be positive) for {event_type}"
                )

        if event_type == "PRODUCT_MOVED":
            if not event.product_id:
                raise EventValidationError("Missing product_id for PRODUCT_MOVED")
            if not event.zone_id:
                raise EventValidationError("Missing zone_id (source) for PRODUCT_MOVED")
            if not event.to_zone_id:
                raise EventValidationError("Missing to_zone_id for PRODUCT_MOVED")
            if event.quantity <= 0:
                raise EventValidationError(
                    f"Invalid quantity: {event.quantity} (must be positive) for PRODUCT_MOVED"
                )

        if event_type in ("ORDER_CREATED", "ORDER_COMPLETED"):
            if not event.order_id:
                raise EventValidationError(f"Missing order_id for {event_type}")

    def _get_entity_key(self, event, event_type: str) -> Optional[str]:
        """Get the entity key for out-of-order tracking."""
        if event_type in ("PRODUCT_RECEIVED", "PRODUCT_SHIPPED", "PRODUCT_RESERVED",
                          "PRODUCT_RELEASED", "INVENTORY_COUNTED"):
            return f"{event.product_id}:{event.zone_id}"
        if event_type == "PRODUCT_MOVED":
            return f"{event.product_id}:{event.zone_id}:{event.to_zone_id}"
        if event_type in ("ORDER_CREATED", "ORDER_COMPLETED"):
            return f"order:{event.order_id}"
        return None

    def _handle_product_received(
        self, event, event_type: str, event_timestamp: datetime
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """PRODUCT_RECEIVED: available_quantity += quantity in zone."""
        statements = self.db.build_inventory_update_statements(
            product_id=event.product_id,
            zone_id=event.zone_id,
            available_delta=event.quantity,
            reserved_delta=0,
            event_timestamp=event_timestamp,
            supplier_id=event.supplier_id,
        )

        # Event log
        log_stmt = self.db.build_event_log_statement(
            product_id=event.product_id,
            event_timestamp=event_timestamp,
            event_id=event.event_id,
            event_type=event_type,
            zone_id=event.zone_id,
            quantity=event.quantity,
            details=f"supplier_id={event.supplier_id}" if event.supplier_id else "",
        )
        statements.append(log_stmt)

        return statements

    def _handle_product_shipped(
        self, event, event_type: str, event_timestamp: datetime
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """PRODUCT_SHIPPED: available_quantity -= quantity in zone."""
        statements = self.db.build_inventory_update_statements(
            product_id=event.product_id,
            zone_id=event.zone_id,
            available_delta=-event.quantity,
            reserved_delta=0,
            event_timestamp=event_timestamp,
        )

        log_stmt = self.db.build_event_log_statement(
            product_id=event.product_id,
            event_timestamp=event_timestamp,
            event_id=event.event_id,
            event_type=event_type,
            zone_id=event.zone_id,
            quantity=event.quantity,
        )
        statements.append(log_stmt)

        return statements

    def _handle_product_moved(
        self, event, event_type: str, event_timestamp: datetime
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """PRODUCT_MOVED: -quantity in source zone, +quantity in dest zone."""
        # Decrease in source zone
        statements = self.db.build_inventory_update_statements(
            product_id=event.product_id,
            zone_id=event.zone_id,
            available_delta=-event.quantity,
            reserved_delta=0,
            event_timestamp=event_timestamp,
        )

        # Increase in destination zone
        statements.extend(self.db.build_inventory_update_statements(
            product_id=event.product_id,
            zone_id=event.to_zone_id,
            available_delta=event.quantity,
            reserved_delta=0,
            event_timestamp=event_timestamp,
        ))

        log_stmt = self.db.build_event_log_statement(
            product_id=event.product_id,
            event_timestamp=event_timestamp,
            event_id=event.event_id,
            event_type=event_type,
            zone_id=event.zone_id,
            quantity=event.quantity,
            details=f"to_zone_id={event.to_zone_id}",
        )
        statements.append(log_stmt)

        return statements

    def _handle_product_reserved(
        self, event, event_type: str, event_timestamp: datetime
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """PRODUCT_RESERVED: available -= quantity, reserved += quantity."""
        statements = self.db.build_inventory_update_statements(
            product_id=event.product_id,
            zone_id=event.zone_id,
            available_delta=-event.quantity,
            reserved_delta=event.quantity,
            event_timestamp=event_timestamp,
        )

        log_stmt = self.db.build_event_log_statement(
            product_id=event.product_id,
            event_timestamp=event_timestamp,
            event_id=event.event_id,
            event_type=event_type,
            zone_id=event.zone_id,
            quantity=event.quantity,
        )
        statements.append(log_stmt)

        return statements

    def _handle_product_released(
        self, event, event_type: str, event_timestamp: datetime
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """PRODUCT_RELEASED: reserved -= quantity, available += quantity."""
        statements = self.db.build_inventory_update_statements(
            product_id=event.product_id,
            zone_id=event.zone_id,
            available_delta=event.quantity,
            reserved_delta=-event.quantity,
            event_timestamp=event_timestamp,
        )

        log_stmt = self.db.build_event_log_statement(
            product_id=event.product_id,
            event_timestamp=event_timestamp,
            event_id=event.event_id,
            event_type=event_type,
            zone_id=event.zone_id,
            quantity=event.quantity,
        )
        statements.append(log_stmt)

        return statements

    def _handle_inventory_counted(
        self, event, event_type: str, event_timestamp: datetime
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """INVENTORY_COUNTED: set available_quantity = counted_quantity."""
        # Get current reserved to preserve it
        current = self.db.get_inventory_by_product_zone(event.product_id, event.zone_id)
        current_reserved = current["reserved_quantity"] if current else 0

        statements = self.db.build_inventory_set_statements(
            product_id=event.product_id,
            zone_id=event.zone_id,
            available_quantity=event.quantity,
            reserved_quantity=current_reserved,
            event_timestamp=event_timestamp,
        )

        log_stmt = self.db.build_event_log_statement(
            product_id=event.product_id,
            event_timestamp=event_timestamp,
            event_id=event.event_id,
            event_type=event_type,
            zone_id=event.zone_id,
            quantity=event.quantity,
            details="inventory_count",
        )
        statements.append(log_stmt)

        return statements

    def _handle_order_created(
        self, event, event_type: str, event_timestamp: datetime
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """ORDER_CREATED: create order, reserve items."""
        statements = []

        # Serialize items for storage
        items_json = json.dumps([
            {"product_id": item.product_id, "zone_id": item.zone_id, "quantity": item.quantity}
            for item in event.items
        ])

        # Create order record
        order_stmt = self.db.build_order_statement(
            order_id=event.order_id,
            status="CREATED",
            items=items_json,
            created_at=event_timestamp,
        )
        statements.append(order_stmt)

        # Reserve each item (like PRODUCT_RESERVED for each)
        for item in event.items:
            item_stmts = self.db.build_inventory_update_statements(
                product_id=item.product_id,
                zone_id=item.zone_id,
                available_delta=-item.quantity,
                reserved_delta=item.quantity,
                event_timestamp=event_timestamp,
            )
            statements.extend(item_stmts)

            log_stmt = self.db.build_event_log_statement(
                product_id=item.product_id,
                event_timestamp=event_timestamp,
                event_id=event.event_id,
                event_type="ORDER_CREATED_RESERVE",
                zone_id=item.zone_id,
                quantity=item.quantity,
                details=f"order_id={event.order_id}",
            )
            statements.append(log_stmt)

        return statements

    def _handle_order_completed(
        self, event, event_type: str, event_timestamp: datetime
    ) -> List[Tuple[SimpleStatement, tuple]]:
        """ORDER_COMPLETED: complete order, ship reserved items."""
        statements = []

        # Update order status
        # Read existing order to get items
        existing_order = self.db.get_order(event.order_id)
        items_json = ""
        if existing_order:
            items_json = existing_order["items"]

        order_stmt = self.db.build_order_statement(
            order_id=event.order_id,
            status="COMPLETED",
            items=items_json or "[]",
            created_at=existing_order["created_at"] if existing_order else event_timestamp,
            completed_at=event_timestamp,
        )
        statements.append(order_stmt)

        # Ship reserved items: reserved -= quantity (available stays same, already deducted)
        items = event.items
        if not items and existing_order and existing_order["items"]:
            # Fall back to stored items if not in event
            try:
                stored_items = json.loads(existing_order["items"])
                # Use stored items as a list of dicts
                for item_dict in stored_items:
                    item_stmts = self.db.build_inventory_update_statements(
                        product_id=item_dict["product_id"],
                        zone_id=item_dict["zone_id"],
                        available_delta=0,
                        reserved_delta=-item_dict["quantity"],
                        event_timestamp=event_timestamp,
                    )
                    statements.extend(item_stmts)

                    log_stmt = self.db.build_event_log_statement(
                        product_id=item_dict["product_id"],
                        event_timestamp=event_timestamp,
                        event_id=event.event_id,
                        event_type="ORDER_COMPLETED_SHIP",
                        zone_id=item_dict["zone_id"],
                        quantity=item_dict["quantity"],
                        details=f"order_id={event.order_id}",
                    )
                    statements.append(log_stmt)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse stored order items: %s", e)
        else:
            for item in items:
                item_stmts = self.db.build_inventory_update_statements(
                    product_id=item.product_id,
                    zone_id=item.zone_id,
                    available_delta=0,
                    reserved_delta=-item.quantity,
                    event_timestamp=event_timestamp,
                )
                statements.extend(item_stmts)

                log_stmt = self.db.build_event_log_statement(
                    product_id=item.product_id,
                    event_timestamp=event_timestamp,
                    event_id=event.event_id,
                    event_type="ORDER_COMPLETED_SHIP",
                    zone_id=item.zone_id,
                    quantity=item.quantity,
                    details=f"order_id={event.order_id}",
                )
                statements.append(log_stmt)

        return statements
