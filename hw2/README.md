# Marketplace API

A comprehensive marketplace API built with FastAPI, PostgreSQL, and JWT authentication. This project implements a full-featured e-commerce backend with products, orders, promo codes, and role-based access control.

## Features

- ✅ **OpenAPI 3.0 Specification** - Contract-first API design
- ✅ **CRUD Operations** - Full product management with pagination and filtering
- ✅ **Complex Order Logic** - Rate limiting, stock management, promo codes
- ✅ **JWT Authentication** - Access and refresh tokens
- ✅ **Role-Based Access Control** - USER, SELLER, ADMIN roles
- ✅ **Database Migrations** - Liquibase for schema management
- ✅ **JSON Logging** - Structured API request logging
- ✅ **Error Handling** - Comprehensive error codes and messages
- ✅ **Docker Support** - Easy deployment with docker-compose

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL 15
- **ORM**: SQLAlchemy 2.0
- **Migrations**: Liquibase
- **Authentication**: JWT (python-jose)
- **Validation**: Pydantic v2
- **Containerization**: Docker & Docker Compose

## Project Structure

```
marketplace/
├── liquibase/                  # Database migrations
│   ├── changelog/
│   │   ├── db.changelog-master.yaml
│   │   └── 001-initial-schema.yaml
│   └── liquibase.properties
├── app/
│   ├── routers/               # API endpoints
│   │   ├── auth.py           # Authentication
│   │   ├── products.py       # Product CRUD
│   │   ├── orders.py         # Order management
│   │   └── promo_codes.py    # Promo codes
│   ├── auth.py               # JWT utilities
│   ├── config.py             # Configuration
│   ├── database.py           # Database connection
│   ├── errors.py             # Custom exceptions
│   ├── middleware.py         # Logging middleware
│   ├── models.py             # SQLAlchemy models
│   ├── schemas.py            # Pydantic schemas
│   └── main.py               # FastAPI application
├── openapi/
│   └── openapi.yaml          # OpenAPI specification
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- OR Python 3.11+ and PostgreSQL 15

### Option 1: Docker (Recommended)

1. **Clone and navigate to the project**:
```bash
cd soa/marketplace
```

2. **Start the services**:
```bash
docker-compose up --build
```

3. **Access the API**:
- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Option 2: Local Development

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Set up environment variables**:
```bash
cp .env.example .env
# Edit .env with your database credentials
```

3. **Start PostgreSQL** (if not using Docker):
```bash
# Make sure PostgreSQL is running on localhost:5432
```

4. **Run migrations**:
```bash
# Migrations run automatically with docker-compose
# For manual migration:
docker run --rm -v $(pwd)/liquibase:/liquibase/changelog \
  liquibase/liquibase:4.25 \
  --defaults-file=/liquibase/changelog/liquibase.properties \
  update
```

5. **Start the application**:
```bash
uvicorn app.main:app --reload
```

## API Documentation

### Authentication

#### Register a new user
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123",
    "role": "USER"
  }'
```

#### Login
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123"
  }'
```

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### Products

#### Create a product (SELLER/ADMIN)
```bash
curl -X POST http://localhost:8000/products \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Laptop",
    "description": "High-performance laptop",
    "price": 999.99,
    "stock": 10,
    "category": "Electronics",
    "status": "ACTIVE"
  }'
```

#### List products with filters
```bash
curl "http://localhost:8000/products?page=0&size=20&status=ACTIVE&category=Electronics" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### Get product by ID
```bash
curl http://localhost:8000/products/{product_id} \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### Update product (SELLER/ADMIN)
```bash
curl -X PUT http://localhost:8000/products/{product_id} \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "price": 899.99,
    "stock": 15
  }'
```

#### Delete product (soft delete - SELLER/ADMIN)
```bash
curl -X DELETE http://localhost:8000/products/{product_id} \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Orders

#### Create an order (USER/ADMIN)
```bash
curl -X POST http://localhost:8000/orders \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "product_id": "uuid-here",
        "quantity": 2
      }
    ],
    "promo_code": "SAVE20"
  }'
```

#### Get order by ID
```bash
curl http://localhost:8000/orders/{order_id} \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

#### Update order (only in CREATED status)
```bash
curl -X PUT http://localhost:8000/orders/{order_id} \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "product_id": "uuid-here",
        "quantity": 3
      }
    ]
  }'
```

#### Cancel order
```bash
curl -X POST http://localhost:8000/orders/{order_id}/cancel \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Promo Codes

#### Create promo code (SELLER/ADMIN)
```bash
curl -X POST http://localhost:8000/promo-codes \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "SAVE20",
    "discount_type": "PERCENTAGE",
    "discount_value": 20,
    "min_order_amount": 100,
    "max_uses": 100,
    "valid_from": "2026-01-01T00:00:00Z",
    "valid_until": "2026-12-31T23:59:59Z",
    "active": true
  }'
```

## Business Logic

### Order Creation Flow

1. **Rate Limit Check** - Prevents spam (configurable, default 5 minutes)
2. **Active Order Check** - User can't have multiple active orders
3. **Product Validation** - All products must exist and be ACTIVE
4. **Stock Check** - Sufficient stock for all items
5. **Stock Reservation** - Atomic stock reduction
6. **Price Snapshot** - Current prices frozen in order
7. **Promo Code Application** - Validates and applies discount
8. **Operation Logging** - Records user operation for rate limiting

### Order State Machine

```
CREATED → PAYMENT_PENDING → PAID → SHIPPED → COMPLETED
              ↓
           CANCELED
```

- Orders can only be updated in `CREATED` status
- Orders can be canceled from `CREATED` or `PAYMENT_PENDING`
- Stock is returned on cancellation
- Promo code usage is decremented on cancellation

### Role-Based Access

| Operation | USER | SELLER | ADMIN |
|-----------|------|--------|-------|
| View Products | ✅ | ✅ | ✅ |
| Create Product | ❌ | ✅ (own) | ✅ (any) |
| Update Product | ❌ | ✅ (own) | ✅ (any) |
| Delete Product | ❌ | ✅ (own) | ✅ (any) |
| Create Order | ✅ | ❌ | ✅ |
| View Order | ✅ (own) | ❌ | ✅ (any) |
| Update Order | ✅ (own) | ❌ | ✅ (any) |
| Cancel Order | ✅ (own) | ❌ | ✅ (any) |
| Create Promo Code | ❌ | ✅ | ✅ |

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `PRODUCT_NOT_FOUND` | 404 | Product doesn't exist |
| `PRODUCT_INACTIVE` | 409 | Product is not active |
| `ORDER_NOT_FOUND` | 404 | Order doesn't exist |
| `ORDER_LIMIT_EXCEEDED` | 429 | Rate limit exceeded |
| `ORDER_HAS_ACTIVE` | 409 | User has active order |
| `INVALID_STATE_TRANSITION` | 409 | Invalid order state change |
| `INSUFFICIENT_STOCK` | 409 | Not enough stock |
| `PROMO_CODE_INVALID` | 422 | Invalid promo code |
| `PROMO_CODE_MIN_AMOUNT` | 422 | Order below minimum |
| `ORDER_OWNERSHIP_VIOLATION` | 403 | Not order owner |
| `ACCESS_DENIED` | 403 | Insufficient permissions |
| `VALIDATION_ERROR` | 400 | Input validation failed |
| `TOKEN_EXPIRED` | 401 | Access token expired |
| `TOKEN_INVALID` | 401 | Invalid access token |
| `REFRESH_TOKEN_INVALID` | 401 | Invalid refresh token |

## Database Schema

### Tables

- **users** - User accounts with roles
- **products** - Product catalog
- **orders** - Customer orders
- **order_items** - Order line items with price snapshots
- **promo_codes** - Discount codes
- **user_operations** - Rate limiting tracking

### Indexes

- `products.status` - Fast filtering by status
- `products.category` - Fast filtering by category
- `orders.user_id, orders.status` - Composite index for user orders

## Configuration

Environment variables (`.env`):

```env
DATABASE_URL=postgresql://marketplace:marketplace@localhost:5432/marketplace
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
ORDER_RATE_LIMIT_MINUTES=5
```

## Testing

### Manual Testing

1. Start the application
2. Open Swagger UI at http://localhost:8000/docs
3. Use the interactive documentation to test endpoints

### Database Inspection

```bash
# Connect to PostgreSQL
docker-compose exec db psql -U marketplace -d marketplace

# View tables
\dt

# Query products
SELECT * FROM products;

# Query orders with items
SELECT o.*, oi.* FROM orders o
JOIN order_items oi ON o.id = oi.order_id;
```

## Logging

All API requests are logged in JSON format with:
- `request_id` - Unique request identifier
- `method` - HTTP method
- `endpoint` - Request path
- `status_code` - Response status
- `duration_ms` - Request duration
- `user_id` - Authenticated user (if any)
- `timestamp` - ISO 8601 timestamp
- `request_body` - For mutating requests (passwords masked)

Example log:
```json
{
  "request_id": "123e4567-e89b-12d3-a456-426614174000",
  "method": "POST",
  "endpoint": "/orders",
  "status_code": 201,
  "duration_ms": 45,
  "user_id": "user-uuid",
  "timestamp": "2026-03-04T17:30:00.000Z",
  "request_body": {"items": [...]}
}
```

## Troubleshooting

### Database connection issues
```bash
# Check if PostgreSQL is running
docker-compose ps

# View logs
docker-compose logs db
```

### Migration issues
```bash
# Reset database (WARNING: deletes all data)
docker-compose down -v
docker-compose up --build
```

### Port conflicts
If port 8000 or 5432 is already in use, modify `docker-compose.yml`:
```yaml
ports:
  - "8001:8000"  # Change external port
```

## License

This project is created for educational purposes as part of a Service-Oriented Architecture course.
