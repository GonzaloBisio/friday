"""Registro de tools que FRIDAY expone a Gemini vía function calling."""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Union, get_args, get_origin, get_type_hints

from friday.config import settings
from friday.models import MetricPoint
from friday.storage.metrics_repo import MetricsRepository


class ToolsRegistry:
    """Registro centralizado de funciones que Gemini puede invocar."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}

    def register(self, fn: Callable) -> Callable:
        self._tools[fn.__name__] = fn
        return fn

    @property
    def names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> Callable | None:
        return self._tools.get(name)

    def execute(self, name: str, args: dict[str, Any]) -> Any:
        fn = self._tools.get(name)
        if fn is None:
            raise KeyError(f"Tool '{name}' no registrada")
        return fn(**_coerce_args(fn, args))

    def as_callable_list(self) -> list[Callable]:
        """Retorna las funciones para pasar como tools al SDK de Gemini."""
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def build_registry(repo: MetricsRepository) -> ToolsRegistry:
    """Construye un ToolsRegistry con las tools estándar de lectura."""
    reg = ToolsRegistry()

    def consultar_metricas(
        source: str,
        name: str | None = None,
        horas: int = 24,
        limit: int = 50,
    ) -> str:
        """Consulta métricas almacenadas en FRIDAY.

        Args:
            source: Fuente de métricas — "system", "gemini", "nexcourt" o "productivity".
            name: Nombre específico de la métrica (ej. "cpu_percent", "cost_usd"). Si es None, trae todas las de esa fuente.
            horas: Ventana de tiempo hacia atrás en horas. Default 24.
            limit: Cantidad máxima de puntos a retornar. Default 50.

        Returns:
            JSON con las métricas encontradas.
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=horas)
        points = repo.query(source=source, name=name, start=start, limit=limit)
        return _points_to_json(points)

    def resumen_costos(horas: int = 24) -> str:
        """Resume el costo acumulado de uso de Gemini en un período.

        Args:
            horas: Ventana de tiempo hacia atrás en horas. Default 24.

        Returns:
            JSON con el resumen de costos (total USD, requests, tokens).
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=horas)
        cost_points = repo.query(source="gemini", name="cost_usd", start=start, limit=5000)
        req_points = repo.query(source="gemini", name="requests", start=start, limit=5000)
        tokens_in = repo.query(source="gemini", name="tokens_in", start=start, limit=5000)
        tokens_out = repo.query(source="gemini", name="tokens_out", start=start, limit=5000)

        total_cost = sum(p.value for p in cost_points)
        total_requests = sum(p.value for p in req_points)
        total_in = sum(p.value for p in tokens_in)
        total_out = sum(p.value for p in tokens_out)

        return json.dumps({
            "periodo_horas": horas,
            "costo_total_usd": round(total_cost, 6),
            "requests_totales": int(total_requests),
            "tokens_in_totales": int(total_in),
            "tokens_out_totales": int(total_out),
        })

    reg.register(consultar_metricas)
    reg.register(resumen_costos)

    def obtener_fecha_hora() -> str:
        """Devuelve la fecha y hora actual del sistema.

        Returns:
            JSON con fecha formateada, hora y timestamp ISO.
        """
        now = datetime.now()
        return json.dumps({
            "fecha": now.strftime("%A %d de %B de %Y"),
            "hora": now.strftime("%H:%M:%S"),
            "iso": now.isoformat(),
        })

    reg.register(obtener_fecha_hora)

    # ── Observabilidad NEXCOURT (Fase 1) ──────────────────────────────────────

    def estado_sistemas(sistema: str = "todos") -> str:
        """Resumen del estado actual de los servicios monitoreados.

        Cubre NEXCOURT (microservicios en AWS ECS) y AXIS (containers Docker).
        Por servicio devuelve su salud, CPU %, memoria % y, para NEXCOURT, el
        conteo de tareas (running/desired). Toma el último valor recolectado.

        Args:
            sistema: "todos" (default), "nexcourt" o "axis".

        Returns:
            JSON con la lista de servicios y su estado más reciente.
        """
        sources = {"nexcourt": ["nexcourt"], "axis": ["axis"],
                   "todos": ["nexcourt", "axis"]}.get(sistema, ["nexcourt", "axis"])
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=15)

        resumen = []
        for source in sources:
            points = repo.query(source=source, start=start, limit=5000)
            # orden desc → el primero por (service,name) es el más reciente.
            services: dict[str, dict] = {}
            for p in points:
                bucket = services.setdefault(p.service or "unknown", {})
                if p.name not in bucket:
                    bucket[p.name] = p
            for svc, metrics in sorted(services.items()):
                sp = metrics.get("status")
                entry = {
                    "sistema": source,
                    "servicio": svc,
                    "salud": (sp.tags or {}).get("health", "UNKNOWN") if sp else "SIN_DATOS",
                    "cpu_percent": _val(metrics.get("cpu_percent")),
                    "mem_percent": _val(metrics.get("mem_percent")),
                }
                # tasks_* solo existen en NEXCOURT (ECS). Omitir si no aplica
                # para no confundir al modelo con campos nulos.
                if "tasks_running" in metrics:
                    entry["tasks_running"] = _val(metrics.get("tasks_running"))
                    entry["tasks_desired"] = _val(metrics.get("tasks_desired"))
                resumen.append(entry)
        return json.dumps({"servicios": resumen, "total": len(resumen)}, ensure_ascii=False)

    def metricas_servicio(servicio: str, horas: int = 6, limit: int = 100) -> str:
        """Serie temporal de métricas de un servicio específico (NEXCOURT o AXIS).

        Args:
            servicio: Nombre del servicio/container (ej. "clubs-service", "kong",
                "axis-backend", "axis-keycloak").
            horas: Ventana hacia atrás en horas. Default 6.
            limit: Máximo de puntos a retornar. Default 100.

        Returns:
            JSON con los MetricPoints del servicio en la ventana pedida.
        """
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=horas)
        points = repo.query(service=servicio, start=start, limit=limit)
        return _points_to_json(points)

    reg.register(estado_sistemas)
    reg.register(metricas_servicio)

    # Tools que consultan AWS en vivo — solo tienen sentido en modo cloudwatch.
    if settings.nexcourt_mode == "cloudwatch":

        def alarmas_activas() -> str:
            """Alarmas de CloudWatch que están en estado ALARM ahora mismo.

            Returns:
                JSON con las alarmas activas (vacío si no hay ninguna disparada).
            """
            from friday.collectors.cloudwatch import fetch_active_alarms

            return json.dumps({"alarmas": fetch_active_alarms()}, ensure_ascii=False)

        def errores_recientes(servicio: str, minutos: int = 30) -> str:
            """Mensajes de log con nivel ERROR de un servicio en los últimos minutos.

            Args:
                servicio: Nombre del servicio (ej. "clubs-service", "kong").
                minutos: Ventana hacia atrás en minutos. Default 30.

            Returns:
                JSON con los mensajes de error encontrados.
            """
            from friday.collectors.cloudwatch import fetch_recent_errors

            errores = fetch_recent_errors(servicio, minutes=minutos)
            return json.dumps(
                {"servicio": servicio, "minutos": minutos, "errores": errores},
                ensure_ascii=False,
            )

        reg.register(alarmas_activas)
        reg.register(errores_recientes)

    # Tool de logs de AXIS — solo si AXIS está habilitado.
    if settings.axis_enabled:

        def errores_axis(container: str, minutos: int = 30) -> str:
            """Líneas de log con ERROR/EXCEPTION de un container AXIS.

            Args:
                container: Nombre del container (ej. "axis-backend", "axis-keycloak").
                minutos: Ventana hacia atrás en minutos. Default 30.

            Returns:
                JSON con las líneas de error encontradas.
            """
            from friday.collectors.axis import fetch_axis_errors

            errores = fetch_axis_errors(container, minutes=minutos)
            return json.dumps(
                {"container": container, "minutos": minutos, "errores": errores},
                ensure_ascii=False,
            )

        reg.register(errores_axis)

    return reg


def _val(point: MetricPoint | None) -> float | None:
    return point.value if point is not None else None


# ── Coerción de argumentos (fix sistémico) ─────────────────────────────────
# Ollama/qwen mandan tipos flojos: números como strings ("24"), dicts en vez
# de JSON strings, etc. Sin esto, `json.loads(dict)` y `timedelta(hours="24")`
# revientan en runtime — y ningún test con args bien tipados lo agarra porque
# el LLM real no participa en los tests. La coerción se basa en los type hints
# de la firma de cada tool: el único punto por el que pasan TODAS las calls.

# PEP 604 (`str | None`) produce types.UnionType; Optional[str] produce Union.
# Soportamos ambos para no atarnos a cómo esté escrita la firma.
_UNION_ORIGINS = (Union, getattr(types, "UnionType", Union))


def _coerce_args(fn: Callable, args: dict[str, Any]) -> dict[str, Any]:
    """Coerce los argumentos a los tipos declarados en la firma de `fn`.

    Si la inferencia de tipos falla (forward refs sin resolver, etc.), devuelve
    los args tal cual — coerción es best-effort, no un validador estricto.
    """
    try:
        hints = get_type_hints(fn)
    except Exception:
        return args
    coerced = dict(args)
    for key, value in coerced.items():
        hint = hints.get(key)
        if hint is not None:
            coerced[key] = _coerce_value(value, hint)
    return coerced


def _coerce_value(value: Any, hint: Any) -> Any:
    """Convierte `value` al tipo `hint` cuando Ollama manda algo flojo."""
    if value is None:
        return None

    # Optional[str] / str | None → quedarse con el tipo de adentro.
    origin = get_origin(hint)
    if origin in _UNION_ORIGINS:
        non_none = [a for a in get_args(hint) if a is not type(None)]
        if len(non_none) == 1:
            hint = non_none[0]
            origin = get_origin(hint)
        else:
            return value  # Union compleja: no adivinamos, lo dejamos.

    if hint is str:
        # Caso clave: ejecutar_accion_pc(argumentos: str) recibe un dict de
        # Ollama → lo serializamos a JSON string para que json.loads funcione.
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value if isinstance(value, str) else str(value)

    if hint is int:
        # bool es subtipo de int en Python — no lo rompamos.
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                try:
                    return int(float(value))  # "24.0" → 24
                except ValueError:
                    return value
        if isinstance(value, float):
            return int(value)
        return value

    if hint is float:
        if isinstance(value, (int, str)) and not isinstance(value, bool):
            try:
                return float(value)
            except (ValueError, TypeError):
                return value
        return value

    if hint is bool:
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "on", "si", "sí")
        return value

    return value


def _points_to_json(points: list[MetricPoint]) -> str:
    rows = [
        {
            "timestamp": p.timestamp.isoformat(),
            "source": p.source,
            "name": p.name,
            "value": p.value,
            "unit": p.unit,
            "service": p.service,
        }
        for p in points
    ]
    return json.dumps(rows, ensure_ascii=False)
