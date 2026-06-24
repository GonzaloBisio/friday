"""Integración con la planilla de gastos de Gonzalo (Google Sheets vía Service Account).

Escribe en la pestaña "GASTOS GON", tabla MOVIMIENTOS (header con columnas
Fecha · Tipo · Categoría · Detalle · Monto · Medio de pago). No se appendea al final
del sheet (hay otras tablas debajo): se busca la PRIMERA fila vacía después del header
y se escribe ahí, para no romper las fórmulas del dashboard 50/30/20.

Categorías y medios son una LISTA CERRADA: si no se mapea a un valor exacto, el
dashboard se rompe. Por eso `_match` normaliza acentos/mayúsculas y conoce sinónimos.

Auth: Service Account (headless, sin OAuth). El JSON se referencia desde
settings.google_sheets_credentials; la planilla debe estar compartida con su client_email.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import ValueInputOption

from friday.config import settings

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_TAB = "GASTOS GON"
# Header de la tabla MOVIMIENTOS, normalizado (sin acentos, minúsculas) para detectarlo.
_HEADER = ["fecha", "tipo", "categoria", "detalle", "monto", "medio de pago"]

# Listas cerradas de la planilla (deben matchear EXACTO o se rompe el dashboard).
CATEGORIAS = (
    "Alquiler", "Expensas", "Servicios", "Suscripciones", "Gimnasio", "Súper",
    "Comida afuera / Delivery", "Transporte / Nafta", "Salud", "Salidas / Ocio",
    "Ropa", "Hogar compartido", "Otros",
)
MEDIOS = ("Efectivo", "Débito", "Transferencia", "Tarjeta de Crédito")
TIPOS = ("Gasto", "Ingreso")

# Sinónimos frecuentes (español e inglés, lo que diría Gonzalo) → valor canónico.
_SINONIMOS = {
    "super": "Súper", "supermercado": "Súper", "mercado": "Súper",
    "groceries": "Súper", "supermarket": "Súper",
    "delivery": "Comida afuera / Delivery", "comida": "Comida afuera / Delivery",
    "comida afuera": "Comida afuera / Delivery", "restaurant": "Comida afuera / Delivery",
    "restaurantes": "Comida afuera / Delivery", "food": "Comida afuera / Delivery",
    "comida a domicilio": "Comida afuera / Delivery", "sandwich": "Comida afuera / Delivery",
    "nafta": "Transporte / Nafta", "transporte": "Transporte / Nafta",
    "combustible": "Transporte / Nafta", "uber": "Transporte / Nafta",
    "fuel": "Transporte / Nafta", "transport": "Transporte / Nafta",
    "ocio": "Salidas / Ocio", "salidas": "Salidas / Ocio", "salida": "Salidas / Ocio",
    "subs": "Suscripciones", "suscripcion": "Suscripciones", "subscription": "Suscripciones",
    "gym": "Gimnasio", "gimnasio": "Gimnasio",
    "luz": "Servicios", "gas": "Servicios", "internet": "Servicios", "utilities": "Servicios",
    "alquiler": "Alquiler", "rent": "Alquiler", "salud": "Salud", "health": "Salud",
    "ropa": "Ropa", "clothes": "Ropa", "otros": "Otros", "others": "Otros", "other": "Otros",
    "debito": "Débito", "tarjeta": "Tarjeta de Crédito", "credito": "Tarjeta de Crédito",
    "transferencia": "Transferencia", "efectivo": "Efectivo", "cash": "Efectivo",
}


class GastosError(Exception):
    """Error de la integración de gastos (config, auth o estructura de la planilla)."""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _match(valor: str, opciones: tuple[str, ...]) -> str | None:
    """Mapea un valor flojo a una opción canónica (acentos/mayúsc/sustring/sinónimos)."""
    n = _norm(valor)
    if not n:
        return None
    for o in opciones:
        if _norm(o) == n:
            return o
    if n in _SINONIMOS and _SINONIMOS[n] in opciones:
        return _SINONIMOS[n]
    for o in opciones:                       # substring como último recurso
        if n in _norm(o) or _norm(o) in n:
            return o
    return None


def _parse_monto(x: Any) -> int | None:
    """Convierte el monto a entero de pesos. Tolera '$30.000', '30,000', '15000', 15000."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return int(round(x))
    digits = "".join(c for c in str(x) if c.isdigit())
    return int(digits) if digits else None


@lru_cache(maxsize=1)
def _client() -> gspread.Client:
    cred = settings.google_sheets_credentials
    if not cred:
        raise GastosError("gastos no está configurado (falta GOOGLE_SHEETS_CREDENTIALS en el .env).")
    try:
        creds = Credentials.from_service_account_file(cred, scopes=_SCOPES)
        return gspread.authorize(creds)
    except FileNotFoundError as exc:
        raise GastosError("no encuentro el archivo de credenciales de Google.") from exc
    except Exception as exc:
        raise GastosError(f"no pude autenticar con Google: {exc}") from exc


def _worksheet() -> gspread.Worksheet:
    try:
        sh = _client().open_by_key(settings.gastos_spreadsheet_id)
        return sh.worksheet(_TAB)
    except GastosError:
        raise
    except Exception as exc:
        raise GastosError(f"no pude abrir la planilla: {exc}") from exc


def _find_slot(values: list[list[str]]) -> int:
    """Fila destino (1-based): primera fila totalmente vacía (A-F) tras el header MOVIMIENTOS."""
    header_row = None
    for i, row in enumerate(values, 1):
        if [_norm(c) for c in row[:6]] == _HEADER:
            header_row = i
            break
    if header_row is None:
        raise GastosError("no encontré la tabla de movimientos en la planilla.")
    for i in range(header_row + 1, len(values) + 2):
        row = values[i - 1] if i - 1 < len(values) else []
        if not any((c or "").strip() for c in row[:6]):
            return i
    raise GastosError("la tabla de movimientos no tiene filas libres.")


def cargar_gasto(
    monto: Any,
    categoria: str,
    detalle: str = "",
    medio_pago: str = "Efectivo",
    tipo: str = "Gasto",
) -> str:
    """Carga un gasto (o ingreso) en la planilla de Gonzalo.

    Args:
        monto: Monto en pesos (número; ej. 15000).
        categoria: Categoría. Debe ser una de la lista: Alquiler, Expensas, Servicios,
            Suscripciones, Gimnasio, Súper, Comida afuera / Delivery, Transporte / Nafta,
            Salud, Salidas / Ocio, Ropa, Hogar compartido, Otros.
        detalle: Descripción corta (ej. "Verdulería", "Nafta Shell").
        medio_pago: Efectivo, Débito, Transferencia o Tarjeta de Crédito. Default Efectivo.
        tipo: "Gasto" (default) o "Ingreso".

    Returns:
        Confirmación de lo anotado, o un error honesto.
    """
    m = _parse_monto(monto)
    if m is None or m <= 0:
        return "No entendí el monto. Decímelo como número, por ejemplo 15000."

    t = _match(tipo, TIPOS) or "Gasto"
    cat = _match(categoria, CATEGORIAS)
    if cat is None:
        if t == "Ingreso" and not (categoria or "").strip():
            cat = ""
        else:
            return f"No reconozco la categoría '{categoria}'. Tiene que ser una de: {', '.join(CATEGORIAS)}."
    medio = _match(medio_pago, MEDIOS) or "Efectivo"

    try:
        ws = _worksheet()
        values = ws.get_all_values()
        slot = _find_slot(values)
        fecha = datetime.now().strftime("%d/%m/%Y")
        fila = [fecha, t, cat, (detalle or "").strip(), m, medio]
        ws.update([fila], f"A{slot}:F{slot}", value_input_option=ValueInputOption.user_entered)
    except GastosError as exc:
        return f"No pude cargar el gasto: {exc}"

    destino = f" en {cat}" if cat else ""
    return f"Anotado: {t.lower()} de ${m:,}{destino} ({medio})."


def _parse_monto_texto(texto: str) -> int | None:
    """Extrae el monto en pesos de una frase. Soporta '10k', '10 mil', '10.000', '1 millón'."""
    t = _norm(texto)
    # Alternancia de más largo a más corto: si no, "mil" matchea el prefijo de "millon".
    m = re.search(r"(\d[\d.,]*)\s*(millones|millon|mil|k)?", t)
    if not m:
        return None
    num = m.group(1).replace(".", "").replace(",", "")
    if not num.isdigit():
        return None
    val = int(num)
    mult = m.group(2)
    if mult in ("k", "mil"):
        val *= 1000
    elif mult in ("millon", "millones"):
        val *= 1_000_000
    return val


# Palabras que marcan un INGRESO (si no, se asume Gasto).
_INGRESO_HINTS = ("ingreso", "sueldo", "cobre", "cobré", "income", "salary", "me pagaron")


def registrar_gasto(texto: str) -> str:
    """Registra un gasto (o ingreso) a partir de UNA frase de lo que dijo Gonzalo.

    Pasá la frase tal cual, sin desarmarla. FRIDAY extrae el monto, la categoría y el
    medio de pago. Ej: "10 mil en el súper con débito", "gasté 5000 de nafta".

    La categoría DEBE ser una de esta lista cerrada (no inventes otras): Alquiler,
    Expensas, Servicios, Suscripciones, Gimnasio, Súper, Comida afuera / Delivery,
    Transporte / Nafta, Salud, Salidas / Ocio, Ropa, Hogar compartido, Otros. Incluí
    en la frase la categoría que corresponda con esas palabras (ej. un sándwich afuera
    va en "Comida afuera / Delivery"; nafta en "Transporte / Nafta").

    Args:
        texto: La frase con el gasto/ingreso (monto + categoría + medio de pago).

    Returns:
        Confirmación, o una pregunta si falta el monto o la categoría.
    """
    texto = (texto or "").strip()
    if not texto:
        return "No me dijiste el gasto."
    monto = _parse_monto_texto(texto)
    if monto is None or monto <= 0:
        return "¿De cuánto fue? Decime el monto con el número."
    n = _norm(texto)
    tipo = "Ingreso" if any(h in n for h in _INGRESO_HINTS) else "Gasto"
    cat = _match(texto, CATEGORIAS)
    if cat is None and tipo == "Gasto":
        return f"¿En qué categoría lo anoto? Tiene que ser una de: {', '.join(CATEGORIAS)}."
    medio = _match(texto, MEDIOS) or "Efectivo"
    return cargar_gasto(monto, cat or "", detalle=texto, medio_pago=medio, tipo=tipo)


def ver_gastos() -> str:
    """Devuelve el resumen del mes de la planilla (ingresos, gastos, balance).

    Returns:
        Resumen en texto, o un error honesto.
    """
    try:
        values = _worksheet().get_all_values()
    except GastosError as exc:
        return f"No pude leer los gastos: {exc}"

    def find(label: str) -> str:
        for row in values:
            if row and _norm(row[0]) == _norm(label):
                return (row[1] or "").strip() if len(row) > 1 else ""
        return ""

    mes = (values[0][0].strip() if values and values[0] else "")
    partes = []
    if mes:
        partes.append(mes)
    for etiqueta, label in (("ingresos", "Ingresos del mes"),
                            ("gastos", "Gastos del mes"),
                            ("balance", "Balance (ahorro)")):
        v = find(label)
        if v:
            partes.append(f"{etiqueta} {v}")
    return " · ".join(partes) if partes else "No encontré el resumen en la planilla."


def _rows_after_header(values: list[list[str]], header_first: str) -> list[list[str]]:
    """Filas no vacías que siguen a la fila cuyo primer campo == header_first (normalizado).

    Corta en la primera fila totalmente vacía. Para extraer bloques tipo tabla
    (50/30/20, gasto por categoría) de una hoja con varias tablas apiladas.
    """
    out: list[list[str]] = []
    capturing = False
    for row in values:
        first = _norm(row[0]) if row else ""
        if capturing:
            if not any((c or "").strip() for c in row):
                break
            out.append([(c or "").strip() for c in row])
        elif first == _norm(header_first):
            capturing = True
    return out


def gastos_dashboard_data() -> dict[str, Any]:
    """Lee la pestaña de gastos y devuelve data estructurada para el dashboard.

    Returns:
        dict con mes, resumen, regla 50/30/20, categorías y movimientos.
        Lanza GastosError si no se puede leer.
    """
    values = _worksheet().get_all_values()

    def find(label: str) -> str:
        for row in values:
            if row and _norm(row[0]) == _norm(label):
                return (row[1] or "").strip() if len(row) > 1 else ""
        return ""

    mes = (values[0][0].strip() if values and values[0] else "")
    resumen = {
        "ingresos": find("Ingresos del mes"),
        "gastos": find("Gastos del mes"),
        "balance": find("Balance (ahorro)"),
        "tasa_ahorro": find("Tasa de ahorro"),
    }

    # Bloques tabulares (cada uno: filas tras su header, hasta la primera vacía).
    regla = _rows_after_header(values, "Bloque")            # [bloque, real$, real%, objetivo, estado]
    categorias = _rows_after_header(values, "Categoría")    # [categoria, clasif, gastado, %ingreso]

    # Movimientos: tras el header Fecha·Tipo·Categoría·Detalle·Monto·Medio, hasta vacío.
    movimientos: list[list[str]] = []
    capturing = False
    for row in values:
        if capturing:
            if not any((c or "").strip() for c in row[:6]):
                break
            movimientos.append([(c or "").strip() for c in row[:6]])
        elif [_norm(c) for c in row[:6]] == _HEADER:
            capturing = True

    return {
        "mes": mes,
        "resumen": resumen,
        "regla": regla,
        "categorias": categorias,
        "movimientos": movimientos,
    }
