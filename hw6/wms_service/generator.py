"""Synthetic warehouse event generator that simulates realistic warehouse operations."""

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from wms_service.config import Config
from wms_service.producer import WarehouseEventProducer

logger = logging.getLogger(__name__)


class WarehouseGenerator:
    """Generates realistic synthetic warehouse events."""

    def __init__(self, producer: WarehouseEventProducer, config: Optional[Config] = None):
        self.producer = producer
        self.config = config or Config()
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Generate product and zone IDs
        self.product_ids = [f"SKU-{i:03d}" for i in range(1, self.config.GENERATOR_NUM_PRODUCTS + 1)]
        self.zone_ids = [f"ZONE-{chr(65 + i)}" for i in range(self.config.GENERATOR_NUM_ZONES)]
        self.supplier_ids = [f"SUP-{i:03d}" for i in range(1, 6)]

        # Track inventory state for realistic generation
        self.inventory: Dict[str, Dict[str, int]] = {}  # product_id -> {zone_id -> qty}
        self.pending_orders: List[Dict] = []

    def start(self) -> None:
        """Start the event generator in background."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._generate_loop())
        logger.info(
            "Warehouse generator started: %d products, %d zones, interval=%dms",
            self.config.GENERATOR_NUM_PRODUCTS,
            self.config.GENERATOR_NUM_ZONES,
            self.config.GENERATOR_INTERVAL_MS,
        )

    async def stop(self) -> None:
        """Stop the event generator."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Warehouse generator stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _generate_loop(self) -> None:
        """Main generation loop."""
        interval = self.config.GENERATOR_INTERVAL_MS / 1000.0

        # Seed initial inventory
        await self._seed_inventory()

        while self._running:
            try:
                self._generate_event()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error generating event: %s", e)
                await asyncio.sleep(1)

    async def _seed_inventory(self) -> None:
        """Generate initial PRODUCT_RECEIVED events to seed inventory."""
        logger.info("Seeding initial inventory...")
        now = datetime.now(timezone.utc)

        for product_id in self.product_ids[:5]:
            zone_id = random.choice(self.zone_ids)
            qty = random.randint(50, 200)

            self.producer.publish_event(
                event_type="PRODUCT_RECEIVED",
                product_id=product_id,
                zone_id=zone_id,
                quantity=qty,
                supplier_id=random.choice(self.supplier_ids),
                timestamp=now,
            )

            # Track locally
            if product_id not in self.inventory:
                self.inventory[product_id] = {}
            self.inventory[product_id][zone_id] = (
                self.inventory[product_id].get(zone_id, 0) + qty
            )

        self.producer.flush(timeout=10)
        logger.info("Initial inventory seeded")

    def _get_available(self, product_id: str, zone_id: str) -> int:
        """Get available quantity for a product in a zone."""
        return self.inventory.get(product_id, {}).get(zone_id, 0)

    def _generate_event(self) -> None:
        """Generate a single realistic warehouse event."""
        now = datetime.now(timezone.utc)

        # Choose event type with weights
        event_type = random.choices(
            [
                "PRODUCT_RECEIVED",
                "PRODUCT_SHIPPED",
                "PRODUCT_MOVED",
                "PRODUCT_RESERVED",
                "PRODUCT_RELEASED",
                "INVENTORY_COUNTED",
                "ORDER_CREATED",
                "ORDER_COMPLETED",
            ],
            weights=[0.25, 0.15, 0.10, 0.10, 0.05, 0.05, 0.15, 0.15],
            k=1,
        )[0]

        if event_type == "PRODUCT_RECEIVED":
            product_id = random.choice(self.product_ids)
            zone_id = random.choice(self.zone_ids)
            qty = random.randint(10, 100)

            self.producer.publish_event(
                event_type="PRODUCT_RECEIVED",
                product_id=product_id,
                zone_id=zone_id,
                quantity=qty,
                supplier_id=random.choice(self.supplier_ids),
                timestamp=now,
            )

            if product_id not in self.inventory:
                self.inventory[product_id] = {}
            self.inventory[product_id][zone_id] = (
                self.inventory[product_id].get(zone_id, 0) + qty
            )

        elif event_type == "PRODUCT_SHIPPED":
            # Find a product with inventory
            candidates = [
                (pid, zid, qty)
                for pid, zones in self.inventory.items()
                for zid, qty in zones.items()
                if qty > 0
            ]
            if not candidates:
                return
            product_id, zone_id, available = random.choice(candidates)
            qty = random.randint(1, min(available, 20))

            self.producer.publish_event(
                event_type="PRODUCT_SHIPPED",
                product_id=product_id,
                zone_id=zone_id,
                quantity=qty,
                timestamp=now,
            )
            self.inventory[product_id][zone_id] -= qty

        elif event_type == "PRODUCT_MOVED":
            candidates = [
                (pid, zid, qty)
                for pid, zones in self.inventory.items()
                for zid, qty in zones.items()
                if qty > 0
            ]
            if not candidates:
                return
            product_id, from_zone, available = random.choice(candidates)
            other_zones = [z for z in self.zone_ids if z != from_zone]
            if not other_zones:
                return
            to_zone = random.choice(other_zones)
            qty = random.randint(1, min(available, 15))

            self.producer.publish_event(
                event_type="PRODUCT_MOVED",
                product_id=product_id,
                zone_id=from_zone,
                to_zone_id=to_zone,
                quantity=qty,
                timestamp=now,
            )
            self.inventory[product_id][from_zone] -= qty
            self.inventory[product_id][to_zone] = (
                self.inventory[product_id].get(to_zone, 0) + qty
            )

        elif event_type == "PRODUCT_RESERVED":
            candidates = [
                (pid, zid, qty)
                for pid, zones in self.inventory.items()
                for zid, qty in zones.items()
                if qty > 5
            ]
            if not candidates:
                return
            product_id, zone_id, available = random.choice(candidates)
            qty = random.randint(1, min(available, 10))

            self.producer.publish_event(
                event_type="PRODUCT_RESERVED",
                product_id=product_id,
                zone_id=zone_id,
                quantity=qty,
                timestamp=now,
            )
            self.inventory[product_id][zone_id] -= qty

        elif event_type == "PRODUCT_RELEASED":
            # Release some previously reserved quantity (simulate)
            product_id = random.choice(self.product_ids)
            zone_id = random.choice(self.zone_ids)
            qty = random.randint(1, 5)

            self.producer.publish_event(
                event_type="PRODUCT_RELEASED",
                product_id=product_id,
                zone_id=zone_id,
                quantity=qty,
                timestamp=now,
            )
            if product_id not in self.inventory:
                self.inventory[product_id] = {}
            self.inventory[product_id][zone_id] = (
                self.inventory[product_id].get(zone_id, 0) + qty
            )

        elif event_type == "INVENTORY_COUNTED":
            product_id = random.choice(self.product_ids)
            zone_id = random.choice(self.zone_ids)
            counted = random.randint(0, 100)

            self.producer.publish_event(
                event_type="INVENTORY_COUNTED",
                product_id=product_id,
                zone_id=zone_id,
                quantity=counted,
                timestamp=now,
            )
            if product_id not in self.inventory:
                self.inventory[product_id] = {}
            self.inventory[product_id][zone_id] = counted

        elif event_type == "ORDER_CREATED":
            # Create an order with 1-3 items
            order_id = f"ORD-{uuid4().hex[:8].upper()}"
            num_items = random.randint(1, 3)
            items = []

            for _ in range(num_items):
                candidates = [
                    (pid, zid, qty)
                    for pid, zones in self.inventory.items()
                    for zid, qty in zones.items()
                    if qty > 3
                ]
                if not candidates:
                    break
                product_id, zone_id, available = random.choice(candidates)
                qty = random.randint(1, min(available, 5))
                items.append({
                    "product_id": product_id,
                    "zone_id": zone_id,
                    "quantity": qty,
                })
                self.inventory[product_id][zone_id] -= qty

            if items:
                self.producer.publish_event(
                    event_type="ORDER_CREATED",
                    order_id=order_id,
                    items=items,
                    timestamp=now,
                )
                self.pending_orders.append({"order_id": order_id, "items": items})

        elif event_type == "ORDER_COMPLETED":
            if not self.pending_orders:
                return
            order = self.pending_orders.pop(0)

            self.producer.publish_event(
                event_type="ORDER_COMPLETED",
                order_id=order["order_id"],
                items=order["items"],
                timestamp=now,
            )
