"""Configuration for Movie Service (Producer)."""

import os


class Config:
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")
    KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "movie-events")

    GENERATOR_ENABLED = os.getenv("GENERATOR_ENABLED", "false").lower() == "true"
    GENERATOR_INTERVAL_MS = int(os.getenv("GENERATOR_INTERVAL_MS", "500"))
    GENERATOR_NUM_USERS = int(os.getenv("GENERATOR_NUM_USERS", "50"))
    GENERATOR_NUM_MOVIES = int(os.getenv("GENERATOR_NUM_MOVIES", "20"))

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))
