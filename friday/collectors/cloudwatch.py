"""Collector NEXCOURT en AWS — ECS + CloudWatch, 100% read-only.

A diferencia de `nexcourt.py` (que pollea Actuator en hosts locales), este collector
observa los servicios corriendo en **AWS ECS** (cluster `nexcourt-dev-cluster`):

- Estado y conteo de tareas → ECS API (`describe_services`): running/desired/status.
- CPU y memoria por servicio → CloudWatch (`get_metric_data`, namespace AWS/ECS).

Emite con `source="nexcourt"` (igual que el collector local) para reusar el wiring
del dashboard y del WebSocket (`broadcast_service_state` keyea por source).

Credenciales: cadena estándar de boto3. ⚠️ Usar un IAM read-only, NO root.
Permisos mínimos: ecs:DescribeServices, cloudwatch:GetMetricData,
cloudwatch:DescribeAlarms, logs:FilterLogEvents.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from friday.config import settings
from friday.models import MetricPoint

from .base import Collector

logger = logging.getLogger(__name__)

# ECS describe_services acepta hasta 10 servicios por llamada.
_ECS_BATCH = 10
_METRIC_PERIOD_SECONDS = 300  # CloudWatch ECS publica cada 60s; 5m suaviza el ruido.

# Pistas de que el fallo es de AUTENTICACIÓN (token SSO vencido), no un bug. Cuando
# matchea, el collector pausa en vez de spamear tracebacks y ofrece re-login.
_AUTH_HINTS = (
    "loginrefreshrequired", "ssotokenload", "unauthorizedsso", "tokenretrieval",
    "expiredtoken", "accessdenied", "reauthenticate", "expired", "invalidgrant",
)


def _is_auth_error(exc: Exception) -> bool:
    blob = (type(exc).__name__ + " " + str(exc)).lower()
    return any(h in blob for h in _AUTH_HINTS)


# ── Factories de clientes boto3 (lazy, una por uso) ───────────────────────────

def _client(service: str):
    """Crea un cliente boto3 read-only. Import perezoso para no exigir boto3
    si FRIDAY corre en modo direct/kong."""
    import boto3

    return boto3.client(service, region_name=settings.aws_region)


# ── Collector ─────────────────────────────────────────────────────────────────

class CloudWatchCollector(Collector):
    """Observa los servicios ECS de NEXCOURT vía ECS API + CloudWatch."""

    def __init__(
        self,
        cluster: str | None = None,
        services: dict | None = None,
        ecs_client=None,
        cw_client=None,
    ) -> None:
        self._cluster = cluster or settings.nexcourt_ecs_cluster
        self._services = services or settings.nexcourt_aws_services
        self._ecs = ecs_client
        self._cw = cw_client
        # Estado de auth: cuando el token SSO vence, abrimos un "circuito" con
        # cooldown para no martillar AWS ni spamear el log. `needs_login` se expone
        # al dashboard para ofrecer el botón de re-login.
        self._needs_login = False
        self._logged_auth_warning = False
        self._retry_after = 0.0  # epoch; mientras now < esto y needs_login, se saltea

    @property
    def source(self) -> str:
        return "nexcourt"

    @property
    def interval_seconds(self) -> int:
        return settings.nexcourt_cloudwatch_poll_interval_seconds

    @property
    def needs_login(self) -> bool:
        """True si el token AWS venció y hace falta re-login."""
        return self._needs_login

    def reset_auth(self) -> None:
        """Fuerza un reintento inmediato (lo llama el flujo de login del dashboard)."""
        self._retry_after = 0.0

    def collect(self) -> list[MetricPoint]:
        if not self._services:
            return []

        # Circuito abierto: token vencido y todavía en cooldown → no llamamos a AWS.
        if self._needs_login and time.time() < self._retry_after:
            return []

        try:
            ecs = self._ecs or _client("ecs")
            cw = self._cw or _client("cloudwatch")

            now = MetricPoint.utcnow()
            points: list[MetricPoint] = []
            points.extend(self._collect_status(ecs, now))
            points.extend(self._collect_utilization(cw, now))
            # Éxito → cerramos el circuito (por si veníamos de un token vencido).
            self._needs_login = False
            self._logged_auth_warning = False
            return points
        except Exception as exc:
            if not _is_auth_error(exc):
                raise  # bug real: que base.run() lo logée con traceback
            # Token vencido: pausamos con cooldown y logueamos UNA sola línea limpia.
            self._needs_login = True
            self._retry_after = time.time() + settings.nexcourt_auth_cooldown_seconds
            if not self._logged_auth_warning:
                self._logged_auth_warning = True
                logger.warning(
                    "NEXCOURT (AWS) sin credenciales válidas (%s). Pauso el collector "
                    "y reintento cada %ds; re-logueá con el botón del dashboard o `aws login`.",
                    type(exc).__name__, settings.nexcourt_auth_cooldown_seconds,
                )
            return []

    # ── ECS: estado + conteo de tareas ────────────────────────────────────────

    def _collect_status(self, ecs, now: datetime) -> list[MetricPoint]:
        # logical → ecs name, y el inverso para mapear la respuesta de vuelta.
        ecs_to_logical = {v["ecs"]: logical for logical, v in self._services.items()}
        ecs_names = list(ecs_to_logical.keys())

        points: list[MetricPoint] = []
        for i in range(0, len(ecs_names), _ECS_BATCH):
            batch = ecs_names[i : i + _ECS_BATCH]
            resp = ecs.describe_services(cluster=self._cluster, services=batch)
            for svc in resp.get("services", []):
                logical = ecs_to_logical.get(svc["serviceName"], svc["serviceName"])
                running = float(svc.get("runningCount", 0))
                desired = float(svc.get("desiredCount", 0))
                active = svc.get("status") == "ACTIVE"
                up = active and desired > 0 and running >= desired

                points.append(MetricPoint(
                    timestamp=now, source=self.source, name="status",
                    value=1.0 if up else 0.0, service=logical,
                    tags={"health": "UP" if up else "DOWN"},
                ))
                points.append(MetricPoint(
                    timestamp=now, source=self.source, name="tasks_running",
                    value=running, service=logical, unit="count",
                ))
                points.append(MetricPoint(
                    timestamp=now, source=self.source, name="tasks_desired",
                    value=desired, service=logical, unit="count",
                ))
        return points

    # ── CloudWatch: CPU + memoria por servicio (un solo get_metric_data) ───────

    def _collect_utilization(self, cw, now: datetime) -> list[MetricPoint]:
        queries, query_meta = self._build_metric_queries()
        if not queries:
            return []

        resp = cw.get_metric_data(
            MetricDataQueries=queries,
            StartTime=now - timedelta(seconds=_METRIC_PERIOD_SECONDS * 2),
            EndTime=now,
        )

        points: list[MetricPoint] = []
        for result in resp.get("MetricDataResults", []):
            values = result.get("Values") or []
            if not values:
                continue
            logical, metric_name = query_meta[result["Id"]]
            points.append(MetricPoint(
                timestamp=now, source=self.source, name=metric_name,
                value=round(float(values[0]), 2), service=logical, unit="%",
            ))
        return points

    def _build_metric_queries(self) -> tuple[list[dict], dict[str, tuple[str, str]]]:
        """Arma las queries de get_metric_data. Devuelve (queries, meta por id)."""
        metrics = {"CPUUtilization": "cpu_percent", "MemoryUtilization": "mem_percent"}
        queries: list[dict] = []
        meta: dict[str, tuple[str, str]] = {}

        for idx, (logical, cfg) in enumerate(self._services.items()):
            for cw_metric, friday_name in metrics.items():
                qid = f"q{idx}_{friday_name}"
                meta[qid] = (logical, friday_name)
                queries.append({
                    "Id": qid,
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ECS",
                            "MetricName": cw_metric,
                            "Dimensions": [
                                {"Name": "ClusterName", "Value": self._cluster},
                                {"Name": "ServiceName", "Value": cfg["ecs"]},
                            ],
                        },
                        "Period": _METRIC_PERIOD_SECONDS,
                        "Stat": "Average",
                    },
                    "ReturnData": True,
                })
        return queries, meta


# ── Helpers read-only para las tools del LLM (consultas en vivo) ───────────────

def fetch_active_alarms() -> list[dict]:
    """Alarmas de CloudWatch en estado ALARM. Hoy puede venir vacío (no hay
    alarmas configuradas todavía)."""
    cw = _client("cloudwatch")
    resp = cw.describe_alarms(StateValue="ALARM")
    alarms = resp.get("MetricAlarms", []) + resp.get("CompositeAlarms", [])
    return [
        {
            "nombre": a.get("AlarmName"),
            "estado": a.get("StateValue"),
            "razon": a.get("StateReason"),
            "metrica": a.get("MetricName"),
            "desde": a.get("StateUpdatedTimestamp").isoformat()
            if a.get("StateUpdatedTimestamp") else None,
        }
        for a in alarms
    ]


def fetch_recent_errors(logical_service: str, minutes: int = 30, limit: int = 20) -> list[str]:
    """Mensajes de log con nivel ERROR de un servicio en los últimos `minutes`."""
    cfg = settings.nexcourt_aws_services.get(logical_service)
    if cfg is None:
        raise KeyError(f"Servicio desconocido: {logical_service}")

    logs = _client("logs")
    start_ms = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
    resp = logs.filter_log_events(
        logGroupName=cfg["log_group"],
        startTime=start_ms,
        filterPattern="ERROR",
        limit=limit,
    )
    return [e.get("message", "").rstrip() for e in resp.get("events", [])]
