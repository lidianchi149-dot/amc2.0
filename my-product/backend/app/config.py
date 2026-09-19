from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AMC Simulation API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = Field(
        default="mysql+pymysql://amc_app:change-me@127.0.0.1:3306/amc_simulation?charset=utf8mb4"
    )
    jwt_secret: str = "development-only-change-this-secret"
    jwt_expire_minutes: int = 480
    cors_origins: list[str] = [
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ]

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.app_env == "production" and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
