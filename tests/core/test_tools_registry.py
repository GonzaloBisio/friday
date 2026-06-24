"""Tests para friday.core.tools_registry — ToolsRegistry y tools de lectura."""

import json
from datetime import datetime, timezone

import pytest

from friday.core.tools_registry import (
    ToolsRegistry,
    _coerce_args,
    _coerce_value,
    _points_to_json,
    build_registry,
)
from friday.models import MetricPoint
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository


@pytest.fixture()
def registry():
    return ToolsRegistry()


def _sample_fn(x: int, y: int = 1) -> int:
    """Suma dos números."""
    return x + y


class TestToolsRegistry:
    def test_register_and_list(self, registry):
        registry.register(_sample_fn)
        assert "_sample_fn" in registry.names
        assert len(registry) == 1

    def test_execute_calls_function(self, registry):
        registry.register(_sample_fn)
        result = registry.execute("_sample_fn", {"x": 3, "y": 7})
        assert result == 10

    def test_execute_unknown_tool_raises(self, registry):
        with pytest.raises(KeyError, match="no_existe"):
            registry.execute("no_existe", {})

    def test_contains(self, registry):
        registry.register(_sample_fn)
        assert "_sample_fn" in registry
        assert "otro" not in registry

    def test_get_returns_callable(self, registry):
        registry.register(_sample_fn)
        fn = registry.get("_sample_fn")
        assert fn is _sample_fn

    def test_get_unknown_returns_none(self, registry):
        assert registry.get("nada") is None

    def test_as_callable_list(self, registry):
        registry.register(_sample_fn)
        callables = registry.as_callable_list()
        assert len(callables) == 1
        assert callables[0] is _sample_fn


# ── Coerción de tipos (fix sistémico) ──────────────────────────────────────
# Ollama/qwen mandan tipos flojos: dict donde la firma dice str, "24" donde
# dice int. Estos tests reproducen los DOS bugs reales del log de producción
# (json.loads(dict) y timedelta(hours="24")), que ningún test con args bien
# tipados podía cazar porque el LLM real no participa en la suite.


def _tool_like_ejecutar_accion(accion: str, argumentos: str = "{}") -> str:
    """Misma firma que ejecutar_accion_pc: argumentos es str, pero Ollama manda dict."""
    args = json.loads(argumentos) if argumentos else {}
    return json.dumps({"accion": accion, "args": args})


class TestCoercion:
    def test_dict_argumentos_coerced_to_json_string(self, registry):
        """Bug #1 del log: json.loads(dict) explotaba → abrir_app nunca abría."""
        registry.register(_tool_like_ejecutar_accion)
        result = registry.execute(
            "_tool_like_ejecutar_accion",
            {"accion": "abrir_app", "argumentos": {"nombre": "spotify"}},
        )
        data = json.loads(result)
        assert data["accion"] == "abrir_app"
        assert data["args"] == {"nombre": "spotify"}

    def test_str_horas_coerced_to_int(self, repo_with_data):
        """Bug #2 del log: timedelta(hours='24') explotaba en resumen_costos."""
        reg = build_registry(repo_with_data)
        result = reg.execute("resumen_costos", {"horas": "24"})
        data = json.loads(result)
        assert data["periodo_horas"] == 24
        assert data["costo_total_usd"] == pytest.approx(0.005, rel=1e-4)

    def test_str_limit_coerced_to_int(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("consultar_metricas", {"source": "system", "limit": "5"})
        data = json.loads(result)
        assert len(data) == 2  # hay 2 puntos de system en el fixture

    def test_well_typed_args_still_work(self, repo_with_data):
        """La coerción es idempotente: args bien tipados no cambian ni se rompen."""
        reg = build_registry(repo_with_data)
        result = reg.execute("resumen_costos", {"horas": 24})
        data = json.loads(result)
        assert data["periodo_horas"] == 24

    def test_coerce_value_dict_to_str(self):
        assert _coerce_value({"nombre": "spotify"}, str) == '{"nombre": "spotify"}'

    def test_coerce_value_str_to_int(self):
        assert _coerce_value("24", int) == 24

    def test_coerce_value_float_string_to_int(self):
        assert _coerce_value("24.0", int) == 24

    def test_coerce_value_str_to_float(self):
        assert _coerce_value("3.5", float) == 3.5

    def test_coerce_value_bool_string(self):
        assert _coerce_value("true", bool) is True
        assert _coerce_value("false", bool) is False

    def test_coerce_value_none_stays_none(self):
        assert _coerce_value(None, int) is None

    def test_coerce_value_idempotent_int(self):
        assert _coerce_value(24, int) == 24
        assert isinstance(_coerce_value(24, int), int)

    def test_coerce_value_bool_not_treated_as_int(self):
        # bool es subtipo de int en Python — no debe convertirse a 0/1.
        assert _coerce_value(True, int) is True

    def test_coerce_value_optional_str_with_dict(self):
        from typing import Optional
        assert _coerce_value({"k": 1}, Optional[str]) == '{"k": 1}'

    def test_coerce_value_pep604_union_with_dict(self):
        assert _coerce_value({"k": 1}, str | None) == '{"k": 1}'

    def test_coerce_value_invalid_int_string_left_as_is(self):
        # "abc" no es int → lo dejamos (mejor un error claro del destinatario
        # que un TypeError críptico de la coerción).
        assert _coerce_value("abc", int) == "abc"

    def test_coerce_args_unknown_keys_passed_through(self):
        assert _coerce_args(_sample_fn, {"x": "3", "extra": "pasamanos"}) == {
            "x": 3, "extra": "pasamanos",
        }

    def test_coerce_args_handles_unresolvable_hints(self):
        # Si get_type_hints falla (forward ref roto), devuelve args tal cual.
        def _bad(x: "NonexistentType"):  # noqa
            return x
        assert _coerce_args(_bad, {"x": 1}) == {"x": 1}


@pytest.fixture()
def repo_with_data(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    repo = MetricsRepository(conn)
    now = datetime.now(timezone.utc)
    points = [
        MetricPoint(timestamp=now, source="system", name="cpu_percent", value=45.0, unit="%"),
        MetricPoint(timestamp=now, source="system", name="ram_percent", value=60.0, unit="%"),
        MetricPoint(timestamp=now, source="gemini", name="cost_usd", value=0.005, unit="usd"),
        MetricPoint(timestamp=now, source="gemini", name="requests", value=3.0, unit="count"),
        MetricPoint(timestamp=now, source="gemini", name="tokens_in", value=1500.0, unit="tokens"),
        MetricPoint(timestamp=now, source="gemini", name="tokens_out", value=800.0, unit="tokens"),
    ]
    repo.save_many(points)
    yield repo
    conn.close()


@pytest.fixture()
def base_mode(monkeypatch):
    """Aísla del .env del ambiente: modo direct, AXIS off. Estado determinístico."""
    from friday.core import tools_registry as tr
    monkeypatch.setattr(tr.settings, "nexcourt_mode", "direct")
    monkeypatch.setattr(tr.settings, "axis_enabled", False)


class TestBuildRegistry:
    def test_builds_with_default_tools(self, repo_with_data, base_mode):
        reg = build_registry(repo_with_data)
        assert "consultar_metricas" in reg
        assert "resumen_costos" in reg
        assert "obtener_fecha_hora" in reg
        # Observabilidad (Fase 1) — disponibles en cualquier modo
        assert "estado_sistemas" in reg
        assert "metricas_servicio" in reg
        # Sin cloudwatch ni AXIS, las tools en-vivo NO se registran
        assert "alarmas_activas" not in reg
        assert "errores_recientes" not in reg
        assert "errores_axis" not in reg
        assert len(reg) == 5

    def test_aws_live_tools_registered_in_cloudwatch_mode(self, repo_with_data, monkeypatch):
        from friday.core import tools_registry as tr
        monkeypatch.setattr(tr.settings, "nexcourt_mode", "cloudwatch")
        monkeypatch.setattr(tr.settings, "axis_enabled", False)
        reg = build_registry(repo_with_data)
        assert "alarmas_activas" in reg
        assert "errores_recientes" in reg
        assert len(reg) == 7

    def test_axis_tool_registered_when_enabled(self, repo_with_data, monkeypatch):
        from friday.core import tools_registry as tr
        monkeypatch.setattr(tr.settings, "nexcourt_mode", "direct")
        monkeypatch.setattr(tr.settings, "axis_enabled", True)
        reg = build_registry(repo_with_data)
        assert "errores_axis" in reg
        assert len(reg) == 6


class TestConsultarMetricas:
    def test_returns_json_with_metrics(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("consultar_metricas", {"source": "system"})
        data = json.loads(result)
        assert len(data) == 2
        names = {d["name"] for d in data}
        assert "cpu_percent" in names
        assert "ram_percent" in names

    def test_filters_by_name(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("consultar_metricas", {"source": "system", "name": "cpu_percent"})
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["value"] == 45.0

    def test_empty_source_returns_empty(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("consultar_metricas", {"source": "productivity"})
        data = json.loads(result)
        assert data == []


class TestResumenCostos:
    def test_returns_cost_summary(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("resumen_costos", {})
        data = json.loads(result)
        assert data["costo_total_usd"] == pytest.approx(0.005, rel=1e-4)
        assert data["requests_totales"] == 3
        assert data["tokens_in_totales"] == 1500
        assert data["tokens_out_totales"] == 800

    def test_returns_zeros_when_no_data(self, tmp_path):
        db_path = str(tmp_path / "empty.db")
        conn = get_connection(db_path)
        repo = MetricsRepository(conn)
        reg = build_registry(repo)
        result = reg.execute("resumen_costos", {})
        data = json.loads(result)
        assert data["costo_total_usd"] == 0.0
        assert data["requests_totales"] == 0
        conn.close()

    def test_respects_horas_window(self, repo_with_data):
        reg = build_registry(repo_with_data)
        result = reg.execute("resumen_costos", {"horas": 1})
        data = json.loads(result)
        assert data["costo_total_usd"] == pytest.approx(0.005, rel=1e-4)


@pytest.fixture()
def repo_with_nexcourt(tmp_path):
    db_path = str(tmp_path / "nx.db")
    conn = get_connection(db_path)
    repo = MetricsRepository(conn)
    now = datetime.now(timezone.utc)
    older = now.replace(year=now.year - 1)
    repo.save_many([
        # Punto viejo de clubs que NO debe ganarle al reciente.
        MetricPoint(timestamp=older, source="nexcourt", name="status", value=0.0,
                    service="clubs-service", tags={"health": "DOWN"}),
        MetricPoint(timestamp=now, source="nexcourt", name="status", value=1.0,
                    service="clubs-service", tags={"health": "UP"}),
        MetricPoint(timestamp=now, source="nexcourt", name="cpu_percent", value=12.0,
                    service="clubs-service", unit="%"),
        MetricPoint(timestamp=now, source="nexcourt", name="mem_percent", value=44.0,
                    service="clubs-service", unit="%"),
        MetricPoint(timestamp=now, source="nexcourt", name="status", value=1.0,
                    service="kong", tags={"health": "UP"}),
    ])
    yield repo
    conn.close()


class TestEstadoSistemas:
    def test_returns_latest_status_per_service(self, repo_with_nexcourt):
        reg = build_registry(repo_with_nexcourt)
        data = json.loads(reg.execute("estado_sistemas", {}))
        assert data["total"] == 2
        clubs = next(s for s in data["servicios"] if s["servicio"] == "clubs-service")
        # Gana el punto reciente (UP), no el viejo (DOWN).
        assert clubs["salud"] == "UP"
        assert clubs["cpu_percent"] == 12.0
        assert clubs["mem_percent"] == 44.0

    def test_empty_when_no_nexcourt_data(self, repo_with_data):
        reg = build_registry(repo_with_data)
        data = json.loads(reg.execute("estado_sistemas", {}))
        assert data == {"servicios": [], "total": 0}

    def test_covers_both_systems_and_tags_sistema(self, repo_with_nexcourt):
        now = datetime.now(timezone.utc)
        repo_with_nexcourt.save_many([
            MetricPoint(timestamp=now, source="axis", name="status", value=1.0,
                        service="axis-backend", tags={"health": "healthy"}),
        ])
        reg = build_registry(repo_with_nexcourt)
        data = json.loads(reg.execute("estado_sistemas", {}))
        sistemas = {s["sistema"] for s in data["servicios"]}
        assert sistemas == {"nexcourt", "axis"}

    def test_filters_by_sistema(self, repo_with_nexcourt):
        now = datetime.now(timezone.utc)
        repo_with_nexcourt.save_many([
            MetricPoint(timestamp=now, source="axis", name="status", value=1.0,
                        service="axis-backend", tags={"health": "healthy"}),
        ])
        reg = build_registry(repo_with_nexcourt)
        data = json.loads(reg.execute("estado_sistemas", {"sistema": "axis"}))
        assert all(s["sistema"] == "axis" for s in data["servicios"])
        assert data["total"] == 1


class TestMetricasServicio:
    def test_filters_by_service(self, repo_with_nexcourt):
        reg = build_registry(repo_with_nexcourt)
        data = json.loads(reg.execute("metricas_servicio", {"servicio": "kong"}))
        assert all(d["service"] == "kong" for d in data)
        assert len(data) >= 1


class TestPointsToJson:
    def test_serializes_points(self):
        now = datetime.now(timezone.utc)
        points = [MetricPoint(timestamp=now, source="s", name="n", value=1.0)]
        result = _points_to_json(points)
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["source"] == "s"
        assert data[0]["value"] == 1.0
