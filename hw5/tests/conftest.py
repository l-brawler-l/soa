"""Test fixtures and configuration."""

import os
import time

import pytest

# Default test configuration - uses docker-compose services
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "movie_analytics")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_pass")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "movie_metrics")
POSTGRES_USER = os.getenv("POSTGRES_USER", "metrics_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "metrics_pass")
MOVIE_SERVICE_URL = os.getenv("MOVIE_SERVICE_URL", "http://localhost:8000")
AGGREGATION_SERVICE_URL = os.getenv("AGGREGATION_SERVICE_URL", "http://localhost:8001")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9001")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "movie-analytics")


def wait_for_service(url: str, timeout: int = 60, interval: int = 2) -> bool:
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
        ("Movie Service", MOVIE_SERVICE_URL),
        ("Aggregation Service", AGGREGATION_SERVICE_URL),
    ]

    for name, url in services:
        if not wait_for_service(url, timeout=90):
            pytest.skip(f"{name} not available at {url}")
