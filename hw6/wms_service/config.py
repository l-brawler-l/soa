"""Configuration for WMS Service (Producer)."""

import os


class Config:
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")
    KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "warehouse-events")

    GENERATOR_ENABLED = os.getenv("GENERATOR_ENABLED", "false").lower() == "true"
    GENERATOR_INTERVAL_MS = int(os.getenv("GENERATOR_INTERVAL_MS", "1000"))
    GENERATOR_NUM_PRODUCTS = int(os.getenv("GENERATOR_NUM_PRODUCTS", "10"))
    GENERATOR_NUM_ZONES = int(os.getenv("GENERATOR_NUM_ZONES", "5"))

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
