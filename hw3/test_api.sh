#!/bin/bash

# Test script for Flight Booking System API
# This script demonstrates all API endpoints

BASE_URL="http://localhost:8000"

echo "=========================================="
echo "Flight Booking System - API Test Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print section headers
print_section() {
    echo ""
    echo -e "${BLUE}=========================================="
    echo -e "$1"
    echo -e "==========================================${NC}"
    echo ""
}

# Function to print test results
print_test() {
    echo -e "${GREEN}TEST: $1${NC}"
    echo "Request: $2"
    echo ""
}

# Wait for services to be ready
print_section "Waiting for services to start..."
sleep 5

# Health check
print_section "1. Health Check"
print_test "Check if Booking Service is healthy" "GET /health"
curl -s "$BASE_URL/health" | python3 -m json.tool
echo ""

sleep 1

# Search flights
print_section "2. Search Flights"
print_test "Search flights from SVO to LED" "GET /flights?origin=SVO&destination=LED"
curl -s "$BASE_URL/flights?origin=SVO&destination=LED" | python3 -m json.tool
echo ""

sleep 1

print_test "Search flights with date filter" "GET /flights?origin=SVO&destination=LED&date=2026-04-01"
curl -s "$BASE_URL/flights?origin=SVO&destination=LED&date=2026-04-01" | python3 -m json.tool
echo ""

sleep 1

# Get specific flight
print_section "3. Get Flight Details"
print_test "Get flight by ID" "GET /flights/1"
curl -s "$BASE_URL/flights/1" | python3 -m json.tool
echo ""

sleep 1

# Create booking
print_section "4. Create Booking"
print_test "Create a new booking" "POST /bookings"
BOOKING_RESPONSE=$(curl -s -X POST "$BASE_URL/bookings" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "flight_id": 1,
    "passenger_name": "John Doe",
    "passenger_email": "john@example.com",
    "seat_count": 2
  }')
echo "$BOOKING_RESPONSE" | python3 -m json.tool
BOOKING_ID=$(echo "$BOOKING_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "1")
echo ""

sleep 1

# Get booking
print_section "5. Get Booking"
print_test "Get booking by ID" "GET /bookings/$BOOKING_ID"
curl -s "$BASE_URL/bookings/$BOOKING_ID" | python3 -m json.tool
echo ""

sleep 1

# List bookings
print_section "6. List User Bookings"
print_test "List all bookings for user 1" "GET /bookings?user_id=1"
curl -s "$BASE_URL/bookings?user_id=1" | python3 -m json.tool
echo ""

sleep 1

# Create another booking
print_section "7. Create Another Booking"
print_test "Create second booking" "POST /bookings"
curl -s -X POST "$BASE_URL/bookings" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "flight_id": 2,
    "passenger_name": "Jane Smith",
    "passenger_email": "jane@example.com",
    "seat_count": 1
  }' | python3 -m json.tool
echo ""

sleep 1

# Test idempotency
print_section "8. Test Idempotency"
print_test "Try to create duplicate booking (should fail or return existing)" "POST /bookings"
curl -s -X POST "$BASE_URL/bookings" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "flight_id": 1,
    "passenger_name": "John Doe",
    "passenger_email": "john@example.com",
    "seat_count": 2
  }' | python3 -m json.tool
echo ""

sleep 1

# Cancel booking
print_section "9. Cancel Booking"
print_test "Cancel booking $BOOKING_ID" "POST /bookings/$BOOKING_ID/cancel"
curl -s -X POST "$BASE_URL/bookings/$BOOKING_ID/cancel" | python3 -m json.tool
echo ""

sleep 1

# Verify cancellation
print_section "10. Verify Cancellation"
print_test "Get cancelled booking" "GET /bookings/$BOOKING_ID"
curl -s "$BASE_URL/bookings/$BOOKING_ID" | python3 -m json.tool
echo ""

sleep 1

# Test error cases
print_section "11. Error Cases"

print_test "Get non-existent flight" "GET /flights/99999"
curl -s "$BASE_URL/flights/99999" | python3 -m json.tool
echo ""

sleep 1

print_test "Get non-existent booking" "GET /bookings/99999"
curl -s "$BASE_URL/bookings/99999" | python3 -m json.tool
echo ""

sleep 1

print_test "Create booking with invalid data" "POST /bookings"
curl -s -X POST "$BASE_URL/bookings" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "flight_id": 99999,
    "passenger_name": "Test User",
    "passenger_email": "test@example.com",
    "seat_count": 1
  }' | python3 -m json.tool
echo ""

sleep 1

print_section "Test Complete!"
echo -e "${GREEN}All API endpoints have been tested.${NC}"
echo ""
echo "To view API documentation, visit: http://localhost:8000/docs"
echo ""
