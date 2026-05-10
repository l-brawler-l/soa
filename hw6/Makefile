.PHONY: up down build test logs clean proto health

# Start all services
up:
	docker-compose up -d --build

# Stop all services
down:
	docker-compose down -v

# Build images
build:
	docker-compose build

# Run integration tests (services must be running)
test:
	cd .. && python3 -m pytest hw6/tests/ -v --tb=short

# View logs
logs:
	docker-compose logs -f

# View specific service logs
logs-wms:
	docker-compose logs -f wms-service

logs-consumer:
	docker-compose logs -f consumer-service

logs-kafka:
	docker-compose logs -f kafka-1 kafka-2

logs-cassandra:
	docker-compose logs -f cassandra-1 cassandra-2 cassandra-3

# Clean up everything
clean:
	docker-compose down -v --rmi local
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Generate protobuf code locally
proto:
	pip install grpcio-tools protobuf
	python -m grpc_tools.protoc --proto_path=proto --python_out=wms_service/proto proto/warehouse_events.proto
	python -m grpc_tools.protoc --proto_path=proto --python_out=consumer_service/proto proto/warehouse_events.proto

# Check service health
health:
	@echo "WMS Service:"
	@curl -s http://localhost:8000/health | python3 -m json.tool
	@echo "\nConsumer Service:"
	@curl -s http://localhost:8001/health | python3 -m json.tool

# Check Cassandra cluster status
cassandra-status:
	docker exec cassandra-1 nodetool status

# Publish a test event
test-event:
	curl -X POST http://localhost:8000/events \
		-H "Content-Type: application/json" \
		-d '{"event_type":"PRODUCT_RECEIVED","product_id":"SKU-001","zone_id":"ZONE-A","quantity":100,"supplier_id":"SUP-001"}'

# Query inventory
query-inventory:
	@echo "Inventory for SKU-001:"
	@curl -s http://localhost:8001/inventory/SKU-001 | python3 -m json.tool

# Check metrics
metrics:
	curl -s http://localhost:8001/metrics

# Get schema from Schema Registry
get-schema:
	@curl -s http://localhost:8081/subjects/warehouse-events-value/versions/latest | python3 -m json.tool

# Demonstrate fault tolerance: stop one Cassandra node
stop-cassandra-2:
	docker stop cassandra-2

# Restart Cassandra node
start-cassandra-2:
	docker start cassandra-2
