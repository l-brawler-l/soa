"""Configuration for Booking Service."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Booking Service settings."""

    # Service
    service_name: str = "booking-service"
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    db_host: str = "booking-db"
    db_port: int = 5432
    db_name: str = "booking_db"
    db_user: str = "booking_user"
    db_password: str = "booking_pass"

    # Flight Service gRPC
    flight_service_host: str = "flight-service"
    flight_service_port: int = 50051
    flight_service_api_key: str = "flight-service-secret-key"

    # Retry configuration
    retry_max_attempts: int = 3
    retry_initial_backoff_ms: int = 100
    retry_max_backoff_ms: int = 1000

    # Circuit breaker configuration
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_timeout_seconds: int = 30
    circuit_breaker_half_open_max_calls: int = 1

    @property
    def database_url(self) -> str:
        """Get database URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def flight_service_address(self) -> str:
        """Get Flight Service gRPC address."""
        return f"{self.flight_service_host}:{self.flight_service_port}"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
