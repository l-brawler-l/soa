"""Configuration for Consumer Service."""

import os


class Config:
    KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "warehouse-events")
    KAFKA_DLQ_TOPIC = os.getenv("KAFKA_DLQ_TOPIC", "warehouse-events-dlq")
    KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "warehouse-state-consumer")
    SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")

    CASSANDRA_HOSTS = os.getenv("CASSANDRA_HOSTS", "localhost").split(",")
    CASSANDRA_PORT = int(os.getenv("CASSANDRA_PORT", "9042"))
    CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "warehouse")
    CASSANDRA_REPLICATION_FACTOR = int(os.getenv("CASSANDRA_REPLICATION_FACTOR", "3"))
    # Consistency levels: ONE, QUORUM, ALL
    CASSANDRA_WRITE_CL = os.getenv("CASSANDRA_WRITE_CL", "QUORUM")
    CASSANDRA_READ_CL = os.getenv("CASSANDRA_READ_CL", "ONE")

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8001"))
