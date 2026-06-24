"""Ruta REST de gastos — resumen del mes para el HUD (vista CONTROL).

GET /api/gastos — lee la planilla de Gonzalo y devuelve data estructurada
(mes, resumen ingresos/gastos/balance, regla 50/30/20, categorías). Reusa
gastos_dashboard_data() de la integración. Best-effort: si gastos no está
configurado o falla la auth, devuelve {available:false} con la razón.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gastos"])


@router.get("/gastos")
def get_gastos() -> dict:
    """Resumen de gastos del mes (estructurado). available=False si no se pudo leer."""
    try:
        from friday.integrations.gastos import gastos_dashboard_data
        data = gastos_dashboard_data()
    except Exception as exc:  # noqa: BLE001 — config/auth/estructura: lo reportamos suave
        logger.info("Gastos no disponible: %s", exc)
        return {"available": False, "reason": str(exc)}
    return {"available": True, **data}
