#!/bin/bash
set -e

echo "Waiting for Kafka to be ready..."
sleep 5

echo "Creating Kafka topic warehouse-events..."
kafka-topics --create --if-not-exists \
  --bootstrap-server kafka-1:29092 \
  --topic warehouse-events \
  --partitions 3 \
  --replication-factor 2 \
  --config min.insync.replicas=1

echo "Creating Kafka DLQ topic warehouse-events-dlq..."
kafka-topics --create --if-not-exists \
  --bootstrap-server kafka-1:29092 \
  --topic warehouse-events-dlq \
  --partitions 1 \
  --replication-factor 2 \
  --config min.insync.replicas=1

echo "Registering Protobuf schema V1 in Schema Registry..."

SCHEMA_V1='syntax = \"proto3\"; package warehouse_events; import \"google/protobuf/timestamp.proto\"; enum EventType { EVENT_TYPE_UNSPECIFIED = 0; PRODUCT_RECEIVED = 1; PRODUCT_SHIPPED = 2; PRODUCT_MOVED = 3; PRODUCT_RESERVED = 4; PRODUCT_RELEASED = 5; INVENTORY_COUNTED = 6; ORDER_CREATED = 7; ORDER_COMPLETED = 8; } message OrderItem { string product_id = 1; string zone_id = 2; int32 quantity = 3; } message WarehouseEvent { string event_id = 1; EventType event_type = 2; google.protobuf.Timestamp timestamp = 3; int64 sequence_number = 4; string product_id = 5; string zone_id = 6; int32 quantity = 7; string to_zone_id = 8; string order_id = 9; repeated OrderItem items = 10; string supplier_id = 11; }'

curl -s -X POST http://schema-registry:8081/subjects/warehouse-events-value/versions \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d "{\"schemaType\": \"PROTOBUF\", \"schema\": \"$SCHEMA_V1\"}" || echo "Schema V1 registration failed (non-critical)"

echo ""
echo "Topic and schema setup complete."
kafka-topics --describe --bootstrap-server kafka-1:29092 --topic warehouse-events
kafka-topics --describe --bootstrap-server kafka-1:29092 --topic warehouse-events-dlq
