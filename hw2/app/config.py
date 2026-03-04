import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://marketplace:marketplace@localhost:5432/marketplace"
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ORDER_RATE_LIMIT_MINUTES: int = 5

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
