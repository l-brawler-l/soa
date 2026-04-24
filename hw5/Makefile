.PHONY: up down build test logs clean proto

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
	pip install -r requirements-tests.txt
	cd .. && python -m pytest hw5/tests/ -v --tb=short

# View logs
logs:
	docker-compose logs -f

# View specific service logs
logs-movie:
	docker-compose logs -f movie-service

logs-aggregation:
	docker-compose logs -f aggregation-service

logs-clickhouse:
	docker-compose logs -f clickhouse

logs-kafka:
	docker-compose logs -f kafka-1 kafka-2

# Clean up everything
clean:
	docker-compose down -v --rmi local
	rm -rf movie_service/proto/movie_events_pb2.py
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Generate protobuf code locally
proto:
	pip install grpcio-tools protobuf
	python -m grpc_tools.protoc --proto_path=proto --python_out=movie_service/proto proto/movie_events.proto

# Trigger manual aggregation
aggregate:
	curl -X POST http://localhost:8001/compute

# Trigger manual S3 export
export:
	curl -X POST http://localhost:8001/export

# Publish a test event
test-event:
	curl -X POST http://localhost:8000/events \
		-H "Content-Type: application/json" \
		-d '{"user_id":"test_user","movie_id":"test_movie","event_type":"VIEW_STARTED","device_type":"DESKTOP","session_id":"test_session","progress_seconds":0}'

# Check service health
health:
	@echo "Movie Service:"
	@curl -s http://localhost:8000/health | python3 -m json.tool
	@echo "\nAggregation Service:"
	@curl -s http://localhost:8001/health | python3 -m json.tool
