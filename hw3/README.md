# Flight Booking System - Homework 3

A distributed flight booking system built with microservices architecture, featuring gRPC communication, Redis caching, and advanced resilience patterns.

## Architecture

```
Client (REST) → Booking Service → (gRPC) → Flight Service
                      ↓                          ↓
                 PostgreSQL               PostgreSQL + Redis
```

### Services

- **Booking Service**: REST API for managing flight bookings
- **Flight Service**: gRPC API for managing flights and seat reservations
- **PostgreSQL**: Separate databases for each service
- **Redis**: Caching layer for Flight Service

## Features Implemented

### 1-4 Points (Basic Architecture)
- ✅ **gRPC Contract**: Complete `.proto` definition with business operations
- ✅ **ER Diagram**: 3NF database schema (see `ER_DIAGRAM.md`)
- ✅ **PostgreSQL**: Separate databases with automatic migrations
- ✅ **Inter-service Communication**: gRPC calls between services

### 5-7 Points (Transactions & Caching)
- ✅ **Transactional Integrity**: `SELECT FOR UPDATE` for race condition prevention
- ✅ **Authentication**: API key-based gRPC authentication
- ✅ **Redis Caching**: Cache-Aside pattern with TTL and invalidation

### 8-10 Points (Resilience)
- ✅ **Retry Logic**: Exponential backoff with idempotency
- ✅ **Circuit Breaker**: State machine (CLOSED → OPEN → HALF_OPEN)
- ✅ **Comprehensive Tests**: Unit and integration tests

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development)

### Run the System

```bash
# Start all services
docker-compose up --build

# Or use the Makefile
make up
```

Services will be available at:
- **Booking Service API**: http://localhost:8000
- **Flight Service gRPC**: localhost:50051
- **API Documentation**: http://localhost:8000/docs

### Stop the System

```bash
docker-compose down

# Or
make down
```

## API Examples

### Search Flights

```bash
curl "http://localhost:8000/flights?origin=SVO&destination=LED&date=2026-04-01"
```

### Get Flight Details

```bash
curl "http://localhost:8000/flights/1"
```

### Create Booking

```bash
curl -X POST "http://localhost:8000/bookings" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "flight_id": 1,
    "passenger_name": "John Doe",
    "passenger_email": "john@example.com",
    "seat_count": 2
  }'
```

### Get Booking

```bash
curl "http://localhost:8000/bookings/1"
```

### List User Bookings

```bash
curl "http://localhost:8000/bookings?user_id=1"
```

### Cancel Booking

```bash
curl -X POST "http://localhost:8000/bookings/1/cancel"
```

## Testing

### Run Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Generate protobuf code
python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. ./proto/flight_service.proto

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=flight_service --cov=booking_service --cov-report=html
```

## Project Structure

```
hw3/
├── proto/                      # Protocol Buffer definitions
│   └── flight_service.proto
├── flight_service/             # Flight Service (gRPC)
│   ├── __init__.py
│   ├── config.py              # Configuration
│   ├── models.py              # SQLAlchemy models
│   ├── database.py            # Database connection
│   ├── cache.py               # Redis cache manager
│   ├── auth.py                # gRPC authentication
│   ├── service.py             # gRPC service implementation
│   └── server.py              # gRPC server
├── booking_service/            # Booking Service (REST)
│   ├── __init__.py
│   ├── config.py              # Configuration
│   ├── models.py              # SQLAlchemy models
│   ├── database.py            # Database connection
│   ├── schemas.py             # Pydantic schemas
│   ├── circuit_breaker.py     # Circuit breaker implementation
│   ├── grpc_client.py         # gRPC client with retry
│   └── main.py                # FastAPI application
├── tests/                      # Test suite
│   ├── test_flight_service.py
│   └── test_booking_service.py
├── docker-compose.yml          # Docker Compose configuration
├── Dockerfile.flight           # Flight Service Dockerfile
├── Dockerfile.booking          # Booking Service Dockerfile
├── requirements.txt            # Python dependencies
├── ER_DIAGRAM.md              # Database schema documentation
├── Makefile                    # Build automation
└── README.md                   # This file
```

## Key Implementation Details

### 1. gRPC Contract

The `.proto` file defines business operations:
- `SearchFlights`: Find flights by route and date
- `GetFlight`: Get flight details
- `ReserveSeats`: Atomically reserve seats (idempotent)
- `ReleaseReservation`: Return seats to inventory

### 2. Transactional Integrity

**Flight Service** uses `SELECT FOR UPDATE` to prevent race conditions:

```python
flight = db.query(Flight).filter(
    Flight.id == flight_id
).with_for_update().first()

flight.available_seats -= seat_count
# Create reservation in same transaction
```

### 3. Authentication

gRPC calls are authenticated using API keys in metadata:

```python
metadata = [('x-api-key', 'flight-service-secret-key')]
stub.GetFlight(request, metadata=metadata)
```

### 4. Redis Caching

Cache-Aside pattern with automatic invalidation:

```python
# Check cache
cached = cache.get(f"flight:{flight_id}")
if cached:
    return cached

# Query database
flight = db.query(Flight).get(flight_id)

# Update cache
cache.set(f"flight:{flight_id}", flight, ttl=300)
```

### 5. Retry Logic

Exponential backoff for transient failures:

```python
for attempt in range(max_attempts):
    try:
        return grpc_call()
    except grpc.RpcError as e:
        if e.code() in [UNAVAILABLE, DEADLINE_EXCEEDED]:
            backoff = initial_backoff * (2 ** attempt)
            time.sleep(backoff)
        else:
            raise  # Don't retry non-transient errors
```

### 6. Circuit Breaker

Prevents cascading failures:

```
CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing) → CLOSED
     ↑                                                        ↓
     └────────────────────────────────────────────────────────┘
```

### 7. Idempotency

Both services support idempotent operations:
- **ReserveSeats**: Uses `booking_id` to prevent duplicate reservations
- **CreateBooking**: Uses UUID `booking_id` to prevent duplicate bookings

## Configuration

Environment variables (set in `docker-compose.yml`):

### Flight Service
- `GRPC_PORT`: gRPC server port (default: 50051)
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: Database config
- `REDIS_HOST`, `REDIS_PORT`: Redis config
- `CACHE_TTL`: Cache time-to-live in seconds (default: 300)
- `API_KEY`: Authentication key

### Booking Service
- `HOST`, `PORT`: REST API server config
- `DB_*`: Database configuration
- `FLIGHT_SERVICE_HOST`, `FLIGHT_SERVICE_PORT`: Flight Service address
- `FLIGHT_SERVICE_API_KEY`: Authentication key
- `RETRY_MAX_ATTEMPTS`: Max retry attempts (default: 3)
- `RETRY_INITIAL_BACKOFF_MS`: Initial backoff (default: 100ms)
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD`: Failures before opening (default: 5)
- `CIRCUIT_BREAKER_TIMEOUT_SECONDS`: Timeout before half-open (default: 30)

## Database Schema

See `ER_DIAGRAM.md` for detailed schema documentation including:
- Entity-Relationship diagrams
- 3NF normalization proof
- Constraints and indexes
- Cross-service references

## Error Handling

### gRPC Error Codes
- `NOT_FOUND`: Resource not found
- `RESOURCE_EXHAUSTED`: Not enough seats available
- `INVALID_ARGUMENT`: Invalid request parameters
- `UNAUTHENTICATED`: Missing or invalid API key
- `UNAVAILABLE`: Service temporarily unavailable
- `DEADLINE_EXCEEDED`: Request timeout

### HTTP Status Codes
- `200 OK`: Success
- `201 Created`: Resource created
- `400 Bad Request`: Invalid input
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource conflict (e.g., no seats)
- `503 Service Unavailable`: Circuit breaker open

## Monitoring

### Logs

All services log to stdout with structured logging:

```bash
# View all logs
docker-compose logs -f

# View specific service
docker-compose logs -f booking-service
docker-compose logs -f flight-service
```

### Cache Metrics

Redis cache logs show hit/miss rates:
```
Cache HIT: flight:123
Cache MISS: search:SVO:LED:2026-04-01
Cache SET: flight:123 (TTL: 300s)
```

### Circuit Breaker State

Circuit breaker logs state transitions:
```
Circuit breaker OPEN: 5 failures exceeded threshold
Circuit breaker HALF_OPEN: Testing service recovery
Circuit breaker CLOSED: Service recovered
```

## Development

### Local Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Generate protobuf code
python -m grpc_tools.protoc \
  -I./proto \
  --python_out=. \
  --grpc_python_out=. \
  ./proto/flight_service.proto
```

### Adding Sample Data

Connect to the database and add sample flights:

```bash
docker exec -it flight-db psql -U flight_user -d flight_db
```

```sql
INSERT INTO flights (flight_number, airline, origin, destination,
                     departure_time, arrival_time, total_seats,
                     available_seats, price, status)
VALUES ('SU1234', 'Aeroflot', 'SVO', 'LED',
        '2026-04-01 10:00:00', '2026-04-01 12:00:00',
        100, 100, 5000.0, 'SCHEDULED');
```

## Troubleshooting

### Services won't start
```bash
# Check logs
docker-compose logs

# Rebuild images
docker-compose up --build --force-recreate
```

### Database connection errors
```bash
# Check database health
docker-compose ps

# Restart databases
docker-compose restart flight-db booking-db
```

### gRPC connection refused
- Ensure Flight Service is running: `docker-compose ps flight-service`
- Check API key matches in both services
- Verify network connectivity: `docker-compose exec booking-service ping flight-service`

## License

This project is for educational purposes (Innopolis University, SOA Course).

## Author

Homework 3 - Flight Booking System with gRPC and Redis
