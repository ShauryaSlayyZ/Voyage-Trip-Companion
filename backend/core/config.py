# backend/core/config.py
"""
Central configuration loaded from environment variables / .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os

class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "Voyage Trip Companion API"
    ENV: str = "development"               # development | production

    # --- Itinerary storage ---
    ITINERARY_FILE: str = "itinerary.json" # path relative to project root

    # --- Solver ---
    PLANNING_HORIZON_MINUTES: int = 2880   # 48 hours (supports cross-day)
    SOLVER_MAX_WORKERS: int = 4

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton — safe to import anywhere."""
    return Settings()
