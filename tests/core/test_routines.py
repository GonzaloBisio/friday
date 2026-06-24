"""Tests para friday.core.routines — RoutineEngine (Pilar 5: rutinas)."""

from __future__ import annotations

from friday.core.routines import (
    DEFAULT_ROUTINES,
    Routine,
    RoutineEngine,
    RoutineStep,
    register_routine_tools,
)


class FakeGate:
    """Gate falso: registra las llamadas y devuelve status según `fail_on`."""

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._fail_on = fail_on or set()

    def request(self, action: str, args: dict) -> dict:
        self.calls.append((action, args))
        if action in self._fail_on:
            return {"status": "error", "action": action, "reason": "boom"}
        return {"status": "ok", "action": action, "result": "done"}


def _two_step_routines() -> dict[str, Routine]:
    return {
        "focus": Routine(
            name="focus", description="test",
            steps=(
                RoutineStep("reproducir_spotify", {"consulta": "Tech House", "tipo": "playlist"}),
                RoutineStep("ajustar_volumen", {"porcentaje": 60}),
            ),
        ),
    }


# ── run ─────────────────────────────────────────────────────────────────────

class TestRun:
    def test_runs_steps_in_order(self):
        gate = FakeGate()
        engine = RoutineEngine(gate, _two_step_routines())
        result = engine.run("focus")
        assert result["status"] == "ok"
        assert result["ran"] == 2
        assert result["total"] == 2
        # Orden exacto + args forwardeados.
        assert gate.calls[0] == ("reproducir_spotify", {"consulta": "Tech House", "tipo": "playlist"})
        assert gate.calls[1] == ("ajustar_volumen", {"porcentaje": 60})

    def test_unknown_routine_returns_not_found(self):
        engine = RoutineEngine(FakeGate(), _two_step_routines())
        result = engine.run("inexistente")
        assert result["status"] == "not_found"
        assert "focus" in result["available"]

    def test_best_effort_continues_after_failed_step(self):
        # El primer paso falla; el segundo DEBE ejecutarse igual.
        gate = FakeGate(fail_on={"reproducir_spotify"})
        engine = RoutineEngine(gate, _two_step_routines())
        result = engine.run("focus")
        assert result["status"] == "partial"
        assert result["ran"] == 1
        assert len(gate.calls) == 2  # no abortó: corrió ambos pasos
        assert result["steps"][0]["status"] == "error"
        assert result["steps"][1]["status"] == "ok"

    def test_list_routines(self):
        engine = RoutineEngine(FakeGate(), _two_step_routines())
        names = [r.name for r in engine.list_routines()]
        assert names == ["focus"]


# ── Defaults ────────────────────────────────────────────────────────────────

class TestDefaults:
    def test_default_routines_use_low_risk_spotify_actions(self):
        # Los defaults deben correr fluido por voz: solo acciones que no piden
        # confirmación. Verificamos que las acciones referenciadas existen y tienen sentido.
        actions = {s.action for r in DEFAULT_ROUTINES.values() for s in r.steps}
        assert actions <= {"reproducir_spotify", "ajustar_volumen", "pausar_spotify"}


# ── Tools del LLM ───────────────────────────────────────────────────────────

class TestRoutineTools:
    def _registry(self, engine):
        registered = {}

        class Reg:
            def register(self, fn):
                registered[fn.__name__] = fn

        register_routine_tools(Reg(), engine)
        return registered

    def test_ejecutar_rutina_runs_and_summarizes(self):
        gate = FakeGate()
        engine = RoutineEngine(gate, _two_step_routines())
        tools = self._registry(engine)
        out = tools["ejecutar_rutina"]("focus")
        assert "2/2" in out
        assert len(gate.calls) == 2

    def test_ejecutar_rutina_unknown_lists_available(self):
        engine = RoutineEngine(FakeGate(), _two_step_routines())
        tools = self._registry(engine)
        out = tools["ejecutar_rutina"]("nope")
        assert "focus" in out

    def test_listar_rutinas(self):
        engine = RoutineEngine(FakeGate(), _two_step_routines())
        tools = self._registry(engine)
        assert "focus" in tools["listar_rutinas"]()
