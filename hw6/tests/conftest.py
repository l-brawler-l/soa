"""Test fixtures and configuration."""

import os
import time

import pytest

# Default test configuration - uses docker-compose services
WMS_SERVICE_URL = os.getenv("WMS_SERVICE_URL", "http://localhost:8000")
CONSUMER_SERVICE_URL = os.getenv("CONSUMER_SERVICE_URL", "http://localhost:8001")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
CASSANDRA_HOSTS = os.getenv("CASSANDRA_HOSTS", "localhost").split(",")
CASSANDRA_PORT = int(os.getenv("CASSANDRA_PORT", "9042"))
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "warehouse")


def wait_for_service(url: str, timeout: int = 90, interval: int = 2) -> bool:
    """Wait for an HTTP service to become available."""
    import requests

    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{url}/health", timeout=5)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


@pytest.fixture(scope="session", autouse=True)
def wait_for_services():
    """Wait for all services to be ready before running tests."""
    services = [
        ("WMS Service", WMS_SERVICE_URL),
        ("Consumer Service", CONSUMER_SERVICE_URL),
    ]

    for name, url in services:
        if not wait_for_service(url, timeout=120):
            pytest.skip(f"{name} not available at {url}")
