"""Configuration for Aggregation Service."""

import os


class Config:
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

    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9001")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
    MINIO_BUCKET = os.getenv("MINIO_BUCKET", "movie-analytics")
    MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

    AGGREGATION_INTERVAL_MINUTES = int(os.getenv("AGGREGATION_INTERVAL_MINUTES", "5"))

    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8001"))

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def clickhouse_url(self) -> str:
        return f"http://{self.CLICKHOUSE_USER}:{self.CLICKHOUSE_PASSWORD}@{self.CLICKHOUSE_HOST}:{self.CLICKHOUSE_PORT}/{self.CLICKHOUSE_DB}"
