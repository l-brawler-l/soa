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
	pip install -r requirements.txt
	@echo "Generating protobuf code..."
	python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. ./proto/flight_service.proto
	@echo "Running tests..."
	pytest tests/ -v --cov=flight_service --cov=booking_service

proto:
	python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. ./proto/flight_service.proto

sample-data:
	@echo "Adding sample flight data..."
	@sleep 5  # Wait for services to be ready
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
	@curl -s http://localhost:8000/health | python -m json.tool || echo "Booking Service not responding"
