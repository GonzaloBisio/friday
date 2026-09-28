"""Collector AXIS — containers Docker en un droplet, vía SSH. Read-only.

AXIS corre en un servidor DigitalOcean (no AWS, no Actuator): un puñado de
containers Docker. Se observa por SSH ejecutando `docker ps` + `docker stats`
en el host remoto (alias `axis` en ~/.ssh/config).

Emite con `source="axis"`. Por container: status (running), cpu_percent, mem_percent.

El acceso SSH usa tu key local (~/.ssh) ya autorizada en el droplet: en una máquina
nueva hay que copiar la key y el alias `axis` de ~/.ssh/config (ver docs/MIGRATION.md).
"""

from __future__ import annotations

import logging
import subprocess

from friday.config import settings
from friday.models import MetricPoint

from .base import Collector

logger = logging.getLogger(__name__)

# Un solo round-trip SSH: ps (estado) + stats (cpu/mem), separados por marcador.
_STATS_MARKER = "@@STATS@@"
_REMOTE_CMD = (
    "docker ps -a --format '{{.Names}}|{{.State}}|{{.Status}}'; "
    f"echo '{_STATS_MARKER}'; "
    "docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}'"
)


class AxisCollector(Collector):
    """Observa los containers Docker de AXIS por SSH."""

    def __init__(
        self,
        host: str | None = None,
        containers: list[str] | None = None,
        runner=None,
    ) -> None:
        self._host = host or settings.axis_ssh_host
        self._containers = settings.axis_containers if containers is None else containers
        # runner(remote_cmd) -> stdout. Inyectable para testear sin SSH real.
        self._run = runner or self._ssh_run

    @property
    def source(self) -> str:
        return "axis"

    @property
    def interval_seconds(self) -> int:
        return settings.axis_poll_interval_seconds

    def collect(self) -> list[MetricPoint]:
        if not self._containers:
            return []

        output = self._run(_REMOTE_CMD)
        if output is None:
            return []

        states, stats = _parse_output(output)
        now = MetricPoint.utcnow()
        wanted = set(self._containers)
        points: list[MetricPoint] = []

        for name in self._containers:
            state = states.get(name)  # (state, health) o None si no existe
            running = state is not None and state[0] == "running"
            health = state[1] if state else "absent"
            points.append(MetricPoint(
                timestamp=now, source=self.source, name="status",
                value=1.0 if running else 0.0, service=name,
                tags={"health": health},
            ))
            if running and name in stats:
                cpu, mem = stats[name]
                points.append(MetricPoint(
                    timestamp=now, source=self.source, name="cpu_percent",
                    value=cpu, service=name, unit="%",
                ))
                points.append(MetricPoint(
                    timestamp=now, source=self.source, name="mem_percent",
                    value=mem, service=name, unit="%",
                ))

        # Containers presentes que NO están en la lista → no se reportan (restos).
        _ = wanted
        return points

    def _ssh_run(self, remote_cmd: str) -> str | None:
        try:
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes",
                 "-o", f"ConnectTimeout={settings.axis_ssh_timeout_seconds}",
                 self._host, remote_cmd],
                capture_output=True, text=True,
                timeout=settings.axis_ssh_timeout_seconds + 10,
            )
            if result.returncode != 0:
                logger.warning("AXIS ssh returncode=%d: %s", result.returncode,
                               result.stderr.strip()[:200])
                return None
            return result.stdout
        except Exception as exc:
            logger.warning("AXIS ssh falló: %s", exc)
            return None


# ── Parsing ────────────────────────────────────────────────────────────────────

def _parse_output(output: str) -> tuple[dict, dict]:
    """Separa la salida combinada en (states, stats).

    states: name -> (state, health)     desde `docker ps`
    stats:  name -> (cpu_pct, mem_pct)  desde `docker stats`
    """
    ps_part, _, stats_part = output.partition(_STATS_MARKER)

    states: dict[str, tuple[str, str]] = {}
    for line in ps_part.splitlines():
        parts = line.split("|")
        if len(parts) != 3:
            continue
        name, state, status = (p.strip() for p in parts)
        states[name] = (state, _health_from_status(state, status))

    stats: dict[str, tuple[float, float]] = {}
    for line in stats_part.splitlines():
        parts = line.split("|")
        if len(parts) != 3:
            continue
        name, cpu_s, mem_s = (p.strip() for p in parts)
        cpu = _pct(cpu_s)
        mem = _pct(mem_s)
        if cpu is not None and mem is not None:
            stats[name] = (cpu, mem)

    return states, stats


def _health_from_status(state: str, status: str) -> str:
    """Deriva el health del string de status de docker."""
    low = status.lower()
    if "(unhealthy)" in low:
        return "unhealthy"
    if "(healthy)" in low:
        return "healthy"
    if state == "running":
        return "UP"
    return "DOWN"


def _pct(value: str) -> float | None:
    try:
        return round(float(value.rstrip("%").strip()), 2)
    except (ValueError, AttributeError):
        return None


# ── Helper read-only para tools del LLM (logs en vivo) ─────────────────────────

def fetch_axis_errors(container: str, minutes: int = 30, limit: int = 20) -> list[str]:
    """Líneas de log con ERROR/EXCEPTION de un container en los últimos `minutes`."""
    if container not in settings.axis_containers:
        raise KeyError(f"Container desconocido: {container}")

    remote = (
        f"docker logs --since {minutes}m {container} 2>&1 | "
        f"grep -iE 'error|exception' | tail -n {limit}"
    )
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes",
             "-o", f"ConnectTimeout={settings.axis_ssh_timeout_seconds}",
             settings.axis_ssh_host, remote],
            capture_output=True, text=True,
            timeout=settings.axis_ssh_timeout_seconds + 15,
        )
        return [ln for ln in result.stdout.splitlines() if ln.strip()]
    except Exception as exc:
        logger.warning("AXIS logs falló para %s: %s", container, exc)
        return []
