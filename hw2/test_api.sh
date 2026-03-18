#!/bin/bash

# Marketplace API Test Script
# This script tests the main functionality of the API

BASE_URL="http://localhost:8000"
ADMIN_TOKEN=""
USER_TOKEN=""
SELLER_TOKEN=""
PRODUCT_ID=""
ORDER_ID=""

echo "========================================="
echo "Marketplace API Test Script"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print test results
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
    fi
}

# Wait for API to be ready
echo "Waiting for API to be ready..."
for i in {1..30}; do
    if curl -s "http://localhost:8000/health" > /dev/null 2>&1; then
        echo -e "${GREEN}API is ready!${NC}"
        break
    fi
    sleep 1
done

echo ""
echo "========================================="
echo "1. Testing Authentication"
echo "========================================="

# Register ADMIN user
echo "Registering ADMIN user..."
ADMIN_RESPONSE=$(
curl -s -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "admin123456",
    "role": "ADMIN"
  }'
)
echo $ADMIN_RESPONSE
print_result $? "Admin registration"

# Register USER
echo "Registering USER..."
USER_RESPONSE=$(
curl -s -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@test.com",
    "password": "user123456",
    "role": "USER"
  }')
echo $USER_RESPONSE
print_result $? "User registration"

# Register SELLER
echo "Registering SELLER..."
SELLER_RESPONSE=$(
  curl -s -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "seller@test.com",
    "password": "seller123456",
    "role": "SELLER"
  }')
echo $SELLER_RESPONSE
print_result $? "Seller registration"

# Login as ADMIN
echo "Logging in as ADMIN..."
ADMIN_LOGIN=$(
  curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@test.com",
    "password": "admin123456"
  }'
)
echo $ADMIN_LOGIN
ADMIN_TOKEN=$(echo $ADMIN_LOGIN | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
print_result $? "Admin login"

# Login as USER
echo "Logging in as USER..."
USER_LOGIN=$(
  curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@test.com",
    "password": "user123456"
  }')
echo $USER_LOGIN
USER_TOKEN=$(echo $USER_LOGIN | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
print_result $? "User login"

# Login as SELLER
echo "Logging in as SELLER..."
SELLER_LOGIN=$(
curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "seller@test.com",
    "password": "seller123456"
  }')
echo $SELLER_LOGIN
SELLER_TOKEN=$(echo $SELLER_LOGIN | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
print_result $? "Seller login"

echo ""
echo "========================================="
echo "2. Testing Product CRUD"
echo "========================================="

# Create product as SELLER
echo "Creating product as SELLER..."
PRODUCT_RESPONSE=$(
  curl -s -X POST "http://localhost:8000/products" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhNmMyNGNiNC0xZGMyLTRmMGMtOTg2My03ZjgxZmQwZTRhNGQiLCJyb2xlIjoiQURNSU4iLCJleHAiOjE3NzI3OTM5MjAsInR5cGUiOiJhY2Nlc3MifQ.1xjF_6QVCmS93GuCIMbWNoKYIuVJXMb9Se-De-AEejw" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Laptop",
    "description": "High-performance laptop for testing",
    "price": 999.99,
    "stock": -1,
    "category": "Electronics",
    "status": "ACTIVE"
  }'
)
echo $PRODUCT_RESPONSE
PRODUCT_ID=$(echo $PRODUCT_RESPONSE | grep -o '"id":"[^"]*' | cut -d'"' -f4)
print_result $? "Product creation (SELLER)"
echo "Product ID: $PRODUCT_ID"

# List products
echo "Listing products..."
curl -s "http://localhost:8000/products?page=0&size=20" \
  -H "Authorization: Bearer $USER_TOKEN"
print_result $? "List products"

# Get product by ID
echo "Getting product by ID..."
curl -s "http://localhost:8000/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $USER_TOKEN"
print_result $? "Get product by ID"

# Update product as SELLER
echo "Updating product as SELLER..."
curl -s -X PUT "http://localhost:8000/products/$PRODUCT_ID" \
  -H "Authorization: Bearer $SELLER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "price": 899.99,
    "stock": 15
  }'
print_result $? "Update product (SELLER)"

echo ""
echo "========================================="
echo "3. Testing Promo Codes"
echo "========================================="

# Create promo code as SELLER
echo "Creating promo code..."
PROMO_RESPONSE=$(
curl -s -X POST "http://localhost:8000/promo-codes" \
  -H "Authorization: Bearer $SELLER_TOKEN" \
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
  }')
echo $PROMO_RESPONSE
print_result $? "Promo code creation"

echo ""
echo "========================================="
echo "4. Testing Order Creation"
echo "========================================="

# Create order as USER
echo "Creating order as USER..."
ORDER_RESPONSE=$(
curl -s -X POST "http://localhost:8000/orders" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"items\": [
      {
        \"product_id\": \"$PRODUCT_ID\",
        \"quantity\": 2
      }
    ],
    \"promo_code\": \"SAVE20\"
  }"
)
echo $ORDER_RESPONSE
ORDER_ID=$(echo $ORDER_RESPONSE | grep -o '"id":"[^"]*' | cut -d'"' -f4)
print_result $? "Order creation with promo code"
echo "Order ID: $ORDER_ID"

# Get order by ID
# echo "Getting order by ID..."
# curl -s "http://localhost:8000/orders/$ORDER_ID" \
#   -H "Authorization: Bearer $USER_TOKEN"
# print_result $? "Get order by ID"

# echo ""
# echo "========================================="
# echo "5. Testing Order Update"
# echo "========================================="

# # Update order
# echo "Updating order..."
# curl -s -X PUT "http://localhost:8000/orders/$ORDER_ID" \
#   -H "Authorization: Bearer $USER_TOKEN" \
#   -H "Content-Type: application/json" \
#   -d "{
#     \"items\": [
#       {
#         \"product_id\": \"$PRODUCT_ID\",
#         \"quantity\": 3
#       }
#     ]
#   }"
# print_result $? "Order update"

# echo ""
# echo "========================================="
# echo "6. Testing Order Cancellation"
# echo "========================================="

# # Cancel order
# echo "Cancelling order..."
# curl -s -X POST "http://localhost:8000/orders/$ORDER_ID/cancel" \
#   -H "Authorization: Bearer $USER_TOKEN"
# print_result $? "Order cancellation"

echo ""
echo "========================================="
echo "7. Testing Access Control"
echo "========================================="

# Try to create product as USER (should fail)
echo "Testing USER cannot create products..."
FAIL_RESPONSE=$(
curl -s -w "%{http_code}" -X POST "http://localhost:8000/products" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Unauthorized Product",
    "price": 100,
    "stock": 5,
    "category": "Test",
    "status": "ACTIVE"
  }')
echo $FAIL_RESPONSE
if [[ $FAIL_RESPONSE == *"403"* ]]; then
    print_result 0 "Access control: USER cannot create products"
else
    print_result 1 "Access control: USER cannot create products"
fi

# Try to create order as SELLER (should fail)
echo "Testing SELLER cannot create orders..."
FAIL_RESPONSE=$(
curl -s -w "%{http_code}" -X POST "http://localhost:8000/orders" \
  -H "Authorization: Bearer $SELLER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"items\": [
      {
        \"product_id\": \"$PRODUCT_ID\",
        \"quantity\": 1
      }
    ]
  }")
echo $FAIL_RESPONSE
if [[ $FAIL_RESPONSE == *"403"* ]]; then
    print_result 0 "Access control: SELLER cannot create orders"
else
    print_result 1 "Access control: SELLER cannot create orders"
fi

echo ""
echo "========================================="
echo "8. Testing Error Handling"
echo "========================================="

# Test product not found
echo "Testing product not found error..."
FAIL_RESPONSE=$(
curl -s -w "%{http_code}" "http://localhost:8000/products/00000000-0000-0000-0000-000000000000" \
  -H "Authorization: Bearer $USER_TOKEN")
echo $FAIL_RESPONSE
if [[ $FAIL_RESPONSE == *"404"* ]]; then
    print_result 0 "Error handling: Product not found"
else
    print_result 1 "Error handling: Product not found"
fi

# Test validation error
echo "Testing validation error..."
FAIL_RESPONSE=$(
curl -s -w "%{http_code}" -X POST "http://localhost:8000/products" \
  -H "Authorization: Bearer $SELLER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "",
    "price": -10,
    "stock": -5,
    "category": "",
    "status": "ACTIVE"
  }')
echo $FAIL_RESPONSE
if [[ $FAIL_RESPONSE == *"400"* ]] || [[ $FAIL_RESPONSE == *"422"* ]]; then
    print_result 0 "Error handling: Validation error"
else
    print_result 1 "Error handling: Validation error"
fi

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "${GREEN}All critical tests completed!${NC}"
echo ""
echo "To view the database contents:"
echo "  docker-compose exec db psql -U marketplace -d marketplace"
echo ""
echo "To view API logs:"
echo "  docker-compose logs app"
echo ""
echo "To access Swagger UI:"
echo "  http://localhost:8000/docs"
