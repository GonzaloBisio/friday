"""Tests para friday.integrations.gastos — carga/lectura en Google Sheets.

Se patchea `_worksheet` con un fake (sin red): un get_all_values con la tabla
MOVIMIENTOS y un update mock para verificar dónde y qué se escribe.
"""

from unittest.mock import MagicMock, patch

from friday.integrations import gastos
from friday.integrations.gastos import (
    _find_slot,
    _match,
    _parse_monto,
    _parse_monto_texto,
    cargar_gasto,
    registrar_gasto,
    ver_gastos,
)


def _sheet_values():
    """Hoja mínima: resumen arriba, header MOVIMIENTOS en fila 5, un dato, luego vacías."""
    return [
        ["JUNIO 2026", "", "", "", "", ""],            # 1
        ["RESUMEN DEL MES", "", "", "", "", ""],       # 2
        ["Ingresos del mes", "$3,495,935", "", "", "", ""],  # 3
        ["Gastos del mes", "$2,230,786", "", "", "", ""],    # 4
        ["Fecha", "Tipo", "Categoría", "Detalle", "Monto", "Medio de pago"],  # 5 header
        ["01/06/2026", "Gasto", "Súper", "Verdulería", "$30,000", "Transferencia"],  # 6
        ["", "", "", "", "", ""],                       # 7 ← primera vacía
        ["", "", "", "", "", ""],                       # 8
    ]


def _fake_ws():
    ws = MagicMock()
    ws.get_all_values.return_value = _sheet_values()
    return ws


class TestHelpers:
    def test_find_slot_first_empty_after_header(self):
        assert _find_slot(_sheet_values()) == 7

    def test_match_normaliza_acentos_y_sinonimos(self):
        assert _match("super", gastos.CATEGORIAS) == "Súper"
        assert _match("SÚPER", gastos.CATEGORIAS) == "Súper"
        assert _match("delivery", gastos.CATEGORIAS) == "Comida afuera / Delivery"
        assert _match("nafta", gastos.CATEGORIAS) == "Transporte / Nafta"
        assert _match("xyz", gastos.CATEGORIAS) is None

    def test_parse_monto(self):
        assert _parse_monto(15000) == 15000
        assert _parse_monto("15000") == 15000
        assert _parse_monto("$30.000") == 30000
        assert _parse_monto("inválido") is None


class TestCargarGasto:
    def test_writes_to_first_empty_row(self):
        ws = _fake_ws()
        with patch.object(gastos, "_worksheet", return_value=ws):
            result = cargar_gasto(15000, "super", detalle="Verdulería", medio_pago="debito")
        assert "anotado" in result.lower()
        # Se escribió en A7:F7 (primera vacía), no al final del sheet.
        args, kwargs = ws.update.call_args
        assert args[1] == "A7:F7"
        fila = args[0][0]
        assert fila[1] == "Gasto"
        assert fila[2] == "Súper"          # normalizado
        assert fila[4] == 15000             # monto como número, no string
        assert fila[5] == "Débito"          # sinónimo → canónico

    def test_rejects_unknown_category(self):
        ws = _fake_ws()
        with patch.object(gastos, "_worksheet", return_value=ws):
            result = cargar_gasto(15000, "categoria inexistente")
        assert "no reconozco la categoría" in result.lower()
        ws.update.assert_not_called()

    def test_rejects_bad_amount(self):
        ws = _fake_ws()
        with patch.object(gastos, "_worksheet", return_value=ws):
            result = cargar_gasto("no es plata", "Súper")
        assert "monto" in result.lower()
        ws.update.assert_not_called()

    def test_ingreso_allows_empty_category(self):
        ws = _fake_ws()
        with patch.object(gastos, "_worksheet", return_value=ws):
            result = cargar_gasto(3000000, "", detalle="Sueldo", tipo="Ingreso")
        assert "anotado" in result.lower()
        fila = ws.update.call_args[0][0][0]
        assert fila[1] == "Ingreso"
        assert fila[2] == ""

    def test_config_error_is_honest(self):
        with patch.object(gastos, "_worksheet", side_effect=gastos.GastosError("no está configurado")):
            result = cargar_gasto(1000, "Súper")
        assert "no pude cargar" in result.lower()


class TestParseMontoTexto:
    def test_variants(self):
        assert _parse_monto_texto("10k") == 10000
        assert _parse_monto_texto("10 mil en super") == 10000
        assert _parse_monto_texto("gasté 5000 de nafta") == 5000
        assert _parse_monto_texto("$30.000") == 30000
        assert _parse_monto_texto("1 millon de sueldo") == 1_000_000
        assert _parse_monto_texto("sin numero") is None


class TestRegistrarGasto:
    def test_parses_phrase_and_writes(self):
        ws = _fake_ws()
        with patch.object(gastos, "_worksheet", return_value=ws):
            result = registrar_gasto("10 mil en el super con débito")
        assert "anotado" in result.lower()
        fila = ws.update.call_args[0][0][0]
        assert fila[1] == "Gasto"
        assert fila[2] == "Súper"
        assert fila[4] == 10000
        assert fila[5] == "Débito"

    def test_asks_when_no_amount(self):
        result = registrar_gasto("algo en el super")
        assert "de cuánto" in result.lower()

    def test_asks_when_no_category(self):
        result = registrar_gasto("gasté 5000")
        assert "categoría" in result.lower()

    def test_detects_income(self):
        ws = _fake_ws()
        with patch.object(gastos, "_worksheet", return_value=ws):
            registrar_gasto("cobré 3 millones de sueldo")
        fila = ws.update.call_args[0][0][0]
        assert fila[1] == "Ingreso"


class TestVerGastos:
    def test_returns_summary(self):
        ws = _fake_ws()
        with patch.object(gastos, "_worksheet", return_value=ws):
            result = ver_gastos()
        assert "JUNIO 2026" in result
        assert "ingresos" in result.lower()
        assert "$2,230,786" in result
