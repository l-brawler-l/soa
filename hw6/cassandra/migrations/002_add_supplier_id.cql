-- Cassandra Migration 002: Add supplier_id column (Schema Evolution V2)
-- This migration adds the supplier_id column to all inventory tables
-- for backward-compatible schema evolution.
-- V1 events will have supplier_id = null/empty (default)
-- V2 events will have supplier_id = actual supplier ID

ALTER TABLE warehouse.inventory_by_product_zone ADD supplier_id text;
ALTER TABLE warehouse.inventory_by_product ADD supplier_id text;
ALTER TABLE warehouse.inventory_by_zone ADD supplier_id text;
