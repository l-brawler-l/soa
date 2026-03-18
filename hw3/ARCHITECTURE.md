# Architecture Documentation

## System Overview

The Flight Booking System is a distributed microservices application implementing a flight reservation platform with the following key characteristics:

- **Microservices Architecture**: Two independent services with separate databases
- **gRPC Communication**: High-performance inter-service communication
- **Redis Caching**: Performance optimization with Cache-Aside pattern
- **Resilience Patterns**: Retry logic, circuit breaker, and idempotency
- **Transactional Integrity**: ACID guarantees with SELECT FOR UPDATE

## Architecture Diagram

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTP/REST
       ▼
┌─────────────────────────────────────────┐
│       Booking Service (REST API)        │
│  ┌────────────────────────────────────┐ │
│  │  - FastAPI Application             │ │
│  │  - Circuit Breaker                 │ │
│  │  - Retry Logic                     │ │
│  │  - gRPC Client                     │ │
│  └────────────────────────────────────┘ │
└──────┬──────────────────────────────────┘
       │ gRPC + Auth
       ▼
┌─────────────────────────────────────────┐
│      Flight Service (gRPC Server)       │
│  ┌────────────────────────────────────┐ │
│  │  - gRPC Servicer                   │ │
│  │  - Auth Interceptor                │ │
│  │  - Cache Manager                   │ │
│  │  - Transaction Management          │ │
│  └────────────────────────────────────┘ │
└──────┬──────────────────────┬───────────┘
       │                      │
       ▼                      ▼
┌──────────────┐      ┌──────────────┐
│ PostgreSQL   │      │    Redis     │
│ (Flights)    │      │   (Cache)    │
└──────────────┘      └──────────────┘

┌─────────────────────────────────────────┐
│       Booking Service Database          │
│  ┌────────────────────────────────────┐ │
│  │      PostgreSQL (Bookings)         │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

## Component Details

### 1. Booking Service (REST API)

**Technology Stack:**
- FastAPI (Python web framework)
- SQLAlchemy (ORM)
- PostgreSQL (Database)
- gRPC client

**Responsibilities:**
- Expose REST API for clients
- Manage booking lifecycle
- Communicate with Flight Service via gRPC
- Implement resilience patterns (retry, circuit breaker)

**Key Features:**
- **Circuit Breaker**: Prevents cascading failures
- **Retry Logic**: Exponential backoff for transient failures
- **Idempotency**: UUID-based booking IDs
- **Input Validation**: Pydantic schemas

**Endpoints:**
```
GET  /health                    - Health check
GET  /flights                   - Search flights (proxy to Flight Service)
GET  /flights/{id}              - Get flight details (proxy)
POST /bookings                  - Create booking
GET  /bookings/{id}             - Get booking
GET  /bookings?user_id={id}     - List user bookings
POST /bookings/{id}/cancel      - Cancel booking
```

### 2. Flight Service (gRPC Server)

**Technology Stack:**
- gRPC (Python)
- SQLAlchemy (ORM)
- PostgreSQL (Database)
- Redis (Cache)

**Responsibilities:**
- Manage flight inventory
- Handle seat reservations
- Implement caching strategy
- Ensure transactional integrity

**Key Features:**
- **Authentication**: API key validation via gRPC metadata
- **Caching**: Cache-Aside pattern with automatic invalidation
- **Transactions**: SELECT FOR UPDATE for race condition prevention
- **Idempotency**: Booking ID-based reservation deduplication

**gRPC Methods:**
```
SearchFlights(origin, destination, date?) → List<Flight>
GetFlight(flight_id) → Flight
ReserveSeats(flight_id, seat_count, booking_id) → ReservationResponse
ReleaseReservation(booking_id) → ReleaseResponse
```

### 3. Data Layer

**Flight Service Database:**
- `flights` table: Flight inventory
- `seat_reservations` table: Active reservations

**Booking Service Database:**
- `bookings` table: Customer bookings

**Redis Cache:**
- Flight details: `flight:{id}`
- Search results: `search:{origin}:{destination}:{date}`
- TTL: 5 minutes (300 seconds)

## Design Patterns

### 1. Microservices Pattern

**Benefits:**
- Independent deployment
- Technology flexibility
- Fault isolation
- Scalability

**Implementation:**
- Separate databases (no shared DB)
- API-based communication
- Independent scaling

### 2. Cache-Aside Pattern

**Flow:**
```
1. Check cache
2. If HIT → return cached data
3. If MISS → query database
4. Store in cache with TTL
5. Return data
```

**Invalidation:**
- On mutation (update, reserve, release)
- Pattern-based deletion for search results

### 3. Circuit Breaker Pattern

**States:**
```
CLOSED → OPEN → HALF_OPEN → CLOSED
  ↑                            ↓
  └────────────────────────────┘
```

**Transitions:**
- CLOSED → OPEN: After N failures
- OPEN → HALF_OPEN: After timeout
- HALF_OPEN → CLOSED: On success
- HALF_OPEN → OPEN: On failure

### 4. Retry Pattern

**Strategy:**
- Exponential backoff: 100ms, 200ms, 400ms
- Max 3 attempts
- Only for transient errors (UNAVAILABLE, DEADLINE_EXCEEDED)
- No retry for business errors (NOT_FOUND, RESOURCE_EXHAUSTED)

### 5. Idempotency Pattern

**Implementation:**
- Booking Service: UUID booking_id
- Flight Service: Unique constraint on booking_id
- Duplicate requests return existing resource

## Data Flow

### Create Booking Flow

```
1. Client → POST /bookings
2. Booking Service generates UUID booking_id
3. Booking Service → GetFlight(flight_id) [gRPC]
4. Flight Service checks cache
5. Flight Service returns flight details
6. Booking Service → ReserveSeats(flight_id, seat_count, booking_id) [gRPC]
7. Flight Service:
   a. BEGIN TRANSACTION
   b. SELECT ... FOR UPDATE (lock flight row)
   c. Check available_seats >= seat_count
   d. Decrement available_seats
   e. INSERT seat_reservation
   f. COMMIT TRANSACTION
   g. Invalidate cache
8. Flight Service returns success
9. Booking Service:
   a. Calculate total_price = seat_count * flight.price
   b. INSERT booking
   c. COMMIT
10. Booking Service returns booking to client
```

### Cancel Booking Flow

```
1. Client → POST /bookings/{id}/cancel
2. Booking Service checks booking status = CONFIRMED
3. Booking Service → ReleaseReservation(booking_id) [gRPC]
4. Flight Service:
   a. BEGIN TRANSACTION
   b. SELECT reservation FOR UPDATE
   c. SELECT flight FOR UPDATE
   d. Increment available_seats
   e. UPDATE reservation status = RELEASED
   f. COMMIT TRANSACTION
   g. Invalidate cache
5. Flight Service returns success
6. Booking Service:
   a. UPDATE booking status = CANCELLED
   b. COMMIT
7. Booking Service returns success to client
```

## Resilience & Fault Tolerance

### 1. Database Failures

**Handling:**
- Connection pooling with health checks
- Automatic reconnection
- Transaction rollback on errors

### 2. Redis Failures

**Handling:**
- Graceful degradation (cache miss → DB query)
- No impact on core functionality
- Logged warnings

### 3. Flight Service Unavailable

**Handling:**
- Retry with exponential backoff (3 attempts)
- Circuit breaker opens after 5 failures
- Client receives 503 Service Unavailable

### 4. Race Conditions

**Prevention:**
- SELECT FOR UPDATE locks
- Database-level constraints
- Atomic operations

### 5. Duplicate Requests

**Prevention:**
- Idempotent operations
- Unique constraints on booking_id
- Return existing resource on duplicate

## Security

### 1. Authentication

**Method:** API Key in gRPC metadata

**Implementation:**
```python
metadata = [('x-api-key', 'flight-service-secret-key')]
```

**Validation:**
- gRPC interceptor checks metadata
- Returns UNAUTHENTICATED on failure

### 2. Input Validation

**Booking Service:**
- Pydantic schemas validate all inputs
- Email format validation
- Positive number constraints

**Flight Service:**
- Database constraints (CHECK)
- Business logic validation

### 3. SQL Injection Prevention

**Method:** ORM (SQLAlchemy)
- Parameterized queries
- No raw SQL with user input

## Performance Optimization

### 1. Caching Strategy

**What to Cache:**
- Flight details (frequently accessed)
- Search results (read-heavy)

**TTL:** 5 minutes
- Balance between freshness and performance
- Invalidated on mutations

### 2. Database Optimization

**Indexes:**
- Primary keys (automatic)
- Unique constraints (flight_number, departure_time)
- Foreign keys

**Connection Pooling:**
- Pool size: 10
- Max overflow: 20

### 3. gRPC Performance

**Benefits:**
- Binary protocol (faster than JSON)
- HTTP/2 multiplexing
- Efficient serialization (Protocol Buffers)

## Monitoring & Observability

### 1. Logging

**Levels:**
- INFO: Normal operations
- WARNING: Recoverable errors
- ERROR: Failures

**Key Events:**
- Cache hit/miss
- Circuit breaker state changes
- gRPC calls
- Database transactions

### 2. Health Checks

**Endpoints:**
- Booking Service: GET /health
- Database: pg_isready
- Redis: PING

### 3. Metrics (Future Enhancement)

**Suggested Metrics:**
- Request rate
- Error rate
- Response time (p50, p95, p99)
- Cache hit ratio
- Circuit breaker state
- Database connection pool usage

## Scalability

### Horizontal Scaling

**Booking Service:**
- Stateless design
- Can run multiple instances
- Load balancer required

**Flight Service:**
- Stateless design
- Can run multiple instances
- gRPC load balancing

**Databases:**
- Read replicas for read-heavy workloads
- Connection pooling

**Redis:**
- Redis Cluster for high availability
- Redis Sentinel for failover

### Vertical Scaling

**When to Scale:**
- CPU usage > 70%
- Memory usage > 80%
- Database connections exhausted

## Testing Strategy

### 1. Unit Tests

**Coverage:**
- Model constraints
- Business logic
- Circuit breaker state machine
- Retry logic

### 2. Integration Tests

**Coverage:**
- API endpoints
- Database operations
- gRPC communication

### 3. Load Tests (Future)

**Tools:** Locust, k6
**Scenarios:**
- Concurrent bookings
- Search traffic
- Cancellation flow

## Deployment

### Docker Compose

**Services:**
- booking-service
- flight-service
- booking-db (PostgreSQL)
- flight-db (PostgreSQL)
- redis

**Startup Order:**
1. Databases (with health checks)
2. Redis (with health check)
3. Flight Service (depends on flight-db, redis)
4. Booking Service (depends on booking-db, flight-service)

### Environment Variables

**Configuration:**
- Database credentials
- Service addresses
- API keys
- Retry/circuit breaker parameters

## Future Enhancements

### 1. Advanced Features

- [ ] Payment integration
- [ ] Email notifications
- [ ] Seat selection
- [ ] Multi-leg flights
- [ ] Loyalty program

### 2. Resilience

- [ ] Redis Sentinel/Cluster
- [ ] Database replication
- [ ] Rate limiting
- [ ] API gateway

### 3. Observability

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Distributed tracing (Jaeger)
- [ ] ELK stack for logs

### 4. Security

- [ ] JWT authentication
- [ ] HTTPS/TLS
- [ ] API rate limiting
- [ ] Input sanitization

## Conclusion

This architecture provides a solid foundation for a production-ready flight booking system with:

✅ **Scalability**: Microservices can scale independently
✅ **Reliability**: Circuit breaker and retry patterns
✅ **Performance**: Redis caching and gRPC
✅ **Data Integrity**: Transactions and constraints
✅ **Maintainability**: Clean separation of concerns
✅ **Testability**: Comprehensive test coverage
