"""Configuración centralizada de FRIDAY — lee variables de .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Gemini ---
    gemini_api_key: str = ""
    gemini_model_reasoning: str = "gemini-2.5-pro"
    gemini_model_fast: str = "gemini-2.5-flash"

    # Pricing (USD per 1K tokens) — configurable para ajustar sin tocar código
    gemini_cost_per_1k_input_tokens: float = 0.00125
    gemini_cost_per_1k_output_tokens: float = 0.005

    # --- NEXCOURT ---
    nexcourt_base_url: str = "https://localhost:8443"
    nexcourt_services: list[str] = Field(default_factory=list)
    nexcourt_api_key: str = ""
    nexcourt_poll_interval_seconds: int = 30

    # --- Storage ---
    db_path: str = str(_PROJECT_ROOT / "friday.db")

    # --- System collector ---
    system_poll_interval_seconds: int = 10


settings = Settings()
