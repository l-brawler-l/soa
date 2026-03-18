.PHONY: help up down build logs test clean proto sample-data

help:
	@echo "Flight Booking System - Available commands:"
	@echo "  make up           - Start all services"
	@echo "  make down         - Stop all services"
	@echo "  make build        - Build Docker images"
	@echo "  make logs         - View logs from all services"
	@echo "  make test         - Run tests"
	@echo "  make proto        - Generate protobuf code"
	@echo "  make sample-data  - Add sample flight data"
	@echo "  make clean        - Remove all containers and volumes"

up:
	docker-compose up --build -d
	@echo "Services started!"
	@echo "Booking Service API: http://localhost:8000"
	@echo "API Documentation: http://localhost:8000/docs"
	@echo "Flight Service gRPC: localhost:50051"

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f

logs-booking:
	docker-compose logs -f booking-service

logs-flight:
	docker-compose logs -f flight-service

test:
	@echo "Installing dependencies..."
	pip3 install -r requirements.txt
	@echo "Generating protobuf code..."
	python3 -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. ./proto/flight_service.proto
	@echo "Running tests..."
	pytest tests/ -v

proto:
	python3 -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. ./proto/flight_service.proto

sample-data:
	@echo "Adding sample flight data..."
	@sleep 1  # Wait for services to be ready
	docker exec -i flight-db psql -U flight_user -d flight_db < sample_data.sql || true
	@echo "Sample data added!"

clean:
	docker-compose down -v
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -f *_pb2.py *_pb2_grpc.py

restart:
	make down
	make up

status:
	docker-compose ps

health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health | python3 -m json.tool || echo "Booking Service not responding"

check-tables:
	docker exec -it flight-db psql -U flight_user -d flight_db -c "\dt"

check-flights:
	docker exec flight-db psql -U flight_user -d flight_db -c "SELECT * FROM flights;"

check-reservations:
	docker exec flight-db psql -U flight_user -d flight_db -c "SELECT * FROM seat_reservations;"
