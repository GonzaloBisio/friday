"""Página de Gastos — vista completa de la planilla de Google Sheets.

Lee la pestaña de gastos vía Service Account (gspread) y muestra el resumen del mes,
el semáforo 50/30/20, el gasto por categoría y la tabla de movimientos. Cacheada
(ttl 60s) para no pegarle a la API de Sheets en cada refresco.
"""

from __future__ import annotations

import re

import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="FRIDAY — Gastos", page_icon="💸", layout="wide")

# ── Tema (consistente con el command center) ─────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@400;600;700;900&family=Share+Tech+Mono&display=swap');
.stApp, [data-testid="stAppViewContainer"] { background-color:#0a0e17 !important; color:#e0e6ed !important; }
header[data-testid="stHeader"] { background:#0a0e17 !important; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#0b1023,#080c18) !important; }
[data-testid="stMetricValue"] { font-family:'Exo 2',sans-serif !important; color:#00d4ff !important; }
.gx-title { font-family:'Exo 2',sans-serif; font-weight:900; letter-spacing:4px;
  background:linear-gradient(180deg,#fff,#00d4ff); -webkit-background-clip:text;
  -webkit-text-fill-color:transparent; font-size:30px; }
.gx-card { background:rgba(17,24,39,.92); border:1px solid rgba(0,212,255,.2);
  border-radius:12px; padding:16px; margin-bottom:12px; }
.gx-block { font-family:'Exo 2',sans-serif; font-weight:600; font-size:13px;
  letter-spacing:1px; color:#7a8ba0; text-transform:uppercase; margin-bottom:8px; }
</style>
""", unsafe_allow_html=True)


def _num(s: str) -> float:
    """Convierte '$1,016,635' / '36.2%' a número. 0 si no se puede."""
    digits = re.sub(r"[^\d.-]", "", (s or "").replace(".", "").replace(",", ""))
    try:
        return float(digits)
    except ValueError:
        return 0.0


@st.cache_data(ttl=60, show_spinner="Leyendo tu planilla…")
def _load():
    from friday.integrations.gastos import GastosError, gastos_dashboard_data
    try:
        return gastos_dashboard_data(), None
    except GastosError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, f"error inesperado: {exc}"


data, err = _load()

st.markdown('<div class="gx-title">💸 GASTOS</div>', unsafe_allow_html=True)

if err:
    st.error(f"No pude leer la planilla: {err}")
    st.caption("Revisá GOOGLE_SHEETS_CREDENTIALS en el .env y que la planilla esté "
               "compartida con el service account como Editor.")
    st.stop()

st.caption(data["mes"] or "Mes actual")

# ── Resumen del mes ──────────────────────────────────────────────────────────
r = data["resumen"]
m1, m2, m3, m4 = st.columns(4)
m1.metric("Ingresos", r.get("ingresos") or "—")
m2.metric("Gastos", r.get("gastos") or "—")
m3.metric("Balance", r.get("balance") or "—")
m4.metric("Tasa de ahorro", r.get("tasa_ahorro") or "—")

st.markdown("<br>", unsafe_allow_html=True)
col_left, col_right = st.columns([1, 1.3])

# ── 50/30/20 ─────────────────────────────────────────────────────────────────
with col_left:
    st.markdown('<div class="gx-block">Regla 50 / 30 / 20</div>', unsafe_allow_html=True)
    if data["regla"]:
        for row in data["regla"]:
            bloque = row[0] if len(row) > 0 else ""
            real_pct = row[2] if len(row) > 2 else ""
            objetivo = row[3] if len(row) > 3 else ""
            estado = row[4] if len(row) > 4 else ""
            ok = "✅" in estado
            color = "#00ff88" if ok else "#ff3a3a"
            st.markdown(f"""<div class="gx-card" style="display:flex;justify-content:space-between;
                align-items:center;padding:12px 16px;">
                <span style="font-family:'Exo 2',sans-serif;font-weight:600;">{bloque}</span>
                <span style="font-family:'Share Tech Mono',monospace;">
                    <b style="color:{color};">{real_pct}</b>
                    <span style="color:#7a8ba0;"> / {objetivo}</span> {estado}</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.caption("Sin datos de 50/30/20.")

# ── Gasto por categoría ──────────────────────────────────────────────────────
with col_right:
    st.markdown('<div class="gx-block">Gasto por categoría</div>', unsafe_allow_html=True)
    cats = [(row[0], _num(row[2])) for row in data["categorias"]
            if len(row) > 2 and _num(row[2]) > 0]
    cats.sort(key=lambda x: x[1])
    if cats:
        fig = go.Figure(go.Bar(
            x=[v for _, v in cats], y=[c for c, _ in cats], orientation="h",
            marker=dict(color="#00d4ff"),
        ))
        fig.update_layout(height=max(260, 26 * len(cats)),
            margin=dict(t=10, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(color="#7a8ba0", gridcolor="rgba(0,212,255,.06)"),
            yaxis=dict(color="#e0e6ed"), font=dict(family="Share Tech Mono", size=11))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Sin gastos por categoría todavía.")

# ── Movimientos ──────────────────────────────────────────────────────────────
st.markdown('<div class="gx-block">Movimientos del mes</div>', unsafe_allow_html=True)
movs = data["movimientos"]
if movs:
    cols = ["Fecha", "Tipo", "Categoría", "Detalle", "Monto", "Medio de pago"]
    # Más recientes arriba (la planilla los acumula hacia abajo).
    rows = [m + [""] * (6 - len(m)) for m in movs][::-1]
    st.dataframe(
        [dict(zip(cols, row)) for row in rows],
        use_container_width=True, hide_index=True, height=420,
    )
    st.caption(f"{len(movs)} movimientos cargados este mes.")
else:
    st.caption("Todavía no hay movimientos cargados.")

if st.button("🔄 Actualizar desde la planilla"):
    _load.clear()
    st.rerun()
