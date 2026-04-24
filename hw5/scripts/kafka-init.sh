#!/bin/bash
set -e

echo "Creating Kafka topic movie-events..."
kafka-topics --create --if-not-exists \
  --bootstrap-server kafka-1:29092 \
  --topic movie-events \
  --partitions 3 \
  --replication-factor 2 \
  --config min.insync.replicas=1

echo "Registering Protobuf schema in Schema Registry..."

SCHEMA='syntax = \"proto3\"; package movie_events; import \"google/protobuf/timestamp.proto\"; enum EventType { EVENT_TYPE_UNSPECIFIED = 0; VIEW_STARTED = 1; VIEW_FINISHED = 2; VIEW_PAUSED = 3; VIEW_RESUMED = 4; LIKED = 5; SEARCHED = 6; } enum DeviceType { DEVICE_TYPE_UNSPECIFIED = 0; MOBILE = 1; DESKTOP = 2; TV = 3; TABLET = 4; } message MovieEvent { string event_id = 1; string user_id = 2; string movie_id = 3; EventType event_type = 4; google.protobuf.Timestamp timestamp = 5; DeviceType device_type = 6; string session_id = 7; int32 progress_seconds = 8; }'

curl -s -X POST http://schema-registry:8081/subjects/movie-events-value/versions \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d "{\"schemaType\": \"PROTOBUF\", \"schema\": \"$SCHEMA\"}" || echo "Schema registration failed (non-critical)"

echo ""
echo "Topic and schema setup complete."
kafka-topics --describe --bootstrap-server kafka-1:29092 --topic movie-events
