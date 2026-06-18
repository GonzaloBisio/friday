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
    # Modo de acceso: "direct" (management ports 9081-9087) o "kong" (via gateway)
    nexcourt_mode: str = "direct"

    # Modo "direct": URL base para health (ej. http://localhost)
    nexcourt_direct_host: str = "http://localhost"

    # Modo "kong": URL base del gateway (ej. https://dev-api.nexcourts.com)
    nexcourt_kong_url: str = "https://dev-api.nexcourts.com"

    # Servicios a monitorear con sus puertos de gestión (908x) y paths Kong
    # Formato: {"docker_name": {"mgmt_port": 9081, "kong_path": "clubs"}}
    nexcourt_services_config: dict = Field(default_factory=lambda: {
        "clubs-service":          {"mgmt_port": 9081, "kong_path": "clubs"},
        "reservations-service":   {"mgmt_port": 9082, "kong_path": "reservations"},
        "stock-service":          {"mgmt_port": 9083, "kong_path": "stock"},
        "reports-service":        {"mgmt_port": 9084, "kong_path": "reports"},
        "sports-service":         {"mgmt_port": 9085, "kong_path": "sports"},
        "media-service":          {"mgmt_port": 9086, "kong_path": "media"},
        "notifications-service":  {"mgmt_port": 9087, "kong_path": "notifications"},
    })

    # Legacy: alias plano de nombres de servicio (solo los activos)
    nexcourt_services: list[str] = Field(default_factory=list)
    nexcourt_api_key: str = ""
    nexcourt_poll_interval_seconds: int = 30

    # --- Storage ---
    db_path: str = str(_PROJECT_ROOT / "friday.db")

    # --- System collector ---
    system_poll_interval_seconds: int = 10

    # --- Notification thresholds ---
    notifier_cpu_warn: float = 70.0
    notifier_cpu_crit: float = 90.0
    notifier_ram_warn: float = 80.0
    notifier_ram_crit: float = 95.0
    notifier_disk_warn: float = 85.0
    notifier_disk_crit: float = 95.0
    notifier_gemini_cost_daily_warn: float = 0.50
    notifier_gemini_cost_daily_crit: float = 2.00


settings = Settings()
