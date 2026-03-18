"""Configuration for Flight Service."""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Flight Service settings."""

    # Service
    grpc_port: int = 50051
    service_name: str = "flight-service"

    # Database
    db_host: str = "flight-db"
    db_port: int = 5432
    db_name: str = "flight_db"
    db_user: str = "flight_user"
    db_password: str = "flight_pass"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    cache_ttl: int = 300  # 5 minutes

    # Authentication
    api_key: str = "flight-service-secret-key"

    @property
    def database_url(self) -> str:
        """Get database URL."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
