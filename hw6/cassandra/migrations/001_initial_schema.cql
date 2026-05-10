-- Cassandra Migration 001: Initial Schema
-- Applied automatically by consumer_service on startup

-- Create keyspace with NetworkTopologyStrategy (3-node cluster)
CREATE KEYSPACE IF NOT EXISTS warehouse
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
};

-- Table 1: inventory_by_product_zone
-- Query: SELECT * FROM inventory_by_product_zone WHERE product_id = ? AND zone_id = ?
-- PK: (product_id, zone_id) - allows querying by product+zone
CREATE TABLE IF NOT EXISTS warehouse.inventory_by_product_zone (
    product_id text,
    zone_id text,
    available_quantity int,
    reserved_quantity int,
    last_updated timestamp,
    last_sequence bigint,
    supplier_id text,
    PRIMARY KEY (product_id, zone_id)
);

-- Table 2: inventory_by_product
-- Query: SELECT * FROM inventory_by_product WHERE product_id = ?
-- PK: (product_id), CK: (zone_id) - shows all zones for a product
CREATE TABLE IF NOT EXISTS warehouse.inventory_by_product (
    product_id text,
    zone_id text,
    available_quantity int,
    reserved_quantity int,
    last_updated timestamp,
    supplier_id text,
    PRIMARY KEY (product_id, zone_id)
);

-- Table 3: inventory_by_zone
-- Query: SELECT * FROM inventory_by_zone WHERE zone_id = ?
-- PK: (zone_id), CK: (product_id) - shows all products in a zone
CREATE TABLE IF NOT EXISTS warehouse.inventory_by_zone (
    zone_id text,
    product_id text,
    available_quantity int,
    reserved_quantity int,
    last_updated timestamp,
    supplier_id text,
    PRIMARY KEY (zone_id, product_id)
);

-- Table 4: orders
-- PK: (order_id)
CREATE TABLE IF NOT EXISTS warehouse.orders (
    order_id text,
    status text,
    items text,
    created_at timestamp,
    completed_at timestamp,
    PRIMARY KEY (order_id)
);

-- Table 5: event_log (audit trail)
-- PK: (product_id), CK: (event_timestamp DESC, event_id)
CREATE TABLE IF NOT EXISTS warehouse.event_log (
    product_id text,
    event_timestamp timestamp,
    event_id text,
    event_type text,
    zone_id text,
    quantity int,
    details text,
    PRIMARY KEY (product_id, event_timestamp, event_id)
) WITH CLUSTERING ORDER BY (event_timestamp DESC, event_id ASC);

-- Table 6: processed_events (idempotency tracking)
-- PK: (event_id), TTL = 7 days
CREATE TABLE IF NOT EXISTS warehouse.processed_events (
    event_id text,
    processed_at timestamp,
    PRIMARY KEY (event_id)
) WITH default_time_to_live = 604800;

-- Table 7: entity_timestamps (out-of-order event handling)
-- PK: (entity_key)
CREATE TABLE IF NOT EXISTS warehouse.entity_timestamps (
    entity_key text,
    last_timestamp timestamp,
    last_sequence bigint,
    PRIMARY KEY (entity_key)
);
