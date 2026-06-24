"""FRIDAY Dashboard — Command Center futurista con orbe 3D y animaciones."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as stc

from friday.dashboard.components import (
    friday_orb_html,
    live_mic_visualizer_html,
    scanning_line_css,
    tool_activity_html,
    voice_log_html,
    voice_waveform_html,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB = str(_PROJECT_ROOT / "friday.db")


# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="FRIDAY — Command Center",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Global CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@300;400;500;600;700;800;900&family=Share+Tech+Mono&display=swap');

:root {
    --bg-primary: #0a0e17;
    --bg-card: rgba(17, 24, 39, 0.92);
    --border-glow: rgba(0, 212, 255, 0.2);
    --cyan: #00d4ff;
    --teal: #00ffc8;
    --orange: #ff8c00;
    --red: #ff3a3a;
    --green: #00ff88;
    --text-1: #e0e6ed;
    --text-2: #7a8ba0;
}

/* Global background */
.stApp, [data-testid="stAppViewContainer"], .main, .main .block-container {
    background-color: var(--bg-primary) !important;
    color: var(--text-1) !important;
    max-width: 100% !important;
    padding-top: 1rem !important;
}

header[data-testid="stHeader"] {
    background-color: var(--bg-primary) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1023 0%, #080c18 100%) !important;
    border-right: 1px solid rgba(0,212,255,0.1) !important;
}
[data-testid="stSidebar"] * { color: var(--text-1) !important; }

/* Card base */
.fc {
    background: var(--bg-card);
    border: 1px solid var(--border-glow);
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 12px;
    position: relative;
    overflow: hidden;
    backdrop-filter: blur(10px);
}
.fc::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: 0.6;
}

.fc-title {
    font-family: 'Exo 2', sans-serif;
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: var(--cyan);
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(0,212,255,0.08);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

/* Status elements */
.s-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 12px;
    border-radius: 20px;
    font-family: 'Exo 2', sans-serif;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}
.s-ok { background: rgba(0,255,136,0.08); border: 1px solid rgba(0,255,136,0.25); color: var(--green); }
.s-warn { background: rgba(255,140,0,0.08); border: 1px solid rgba(255,140,0,0.25); color: var(--orange); }
.s-crit { background: rgba(255,58,58,0.08); border: 1px solid rgba(255,58,58,0.25); color: var(--red); }

.dot {
    width: 7px; height: 7px; border-radius: 50%; display: inline-block;
    animation: pulse-d 2s ease-in-out infinite;
}
.dot-g { background: var(--green); box-shadow: 0 0 6px var(--green); }
.dot-o { background: var(--orange); box-shadow: 0 0 6px var(--orange); }
.dot-r { background: var(--red); box-shadow: 0 0 6px var(--red); }
.dot-c { background: var(--cyan); box-shadow: 0 0 6px var(--cyan); }
@keyframes pulse-d { 0%,100%{opacity:1}50%{opacity:0.35} }

/* Overview row items */
.ov-item {
    display: flex; align-items: center; gap: 11px;
    padding: 9px 12px; border-radius: 8px;
    background: rgba(0,212,255,0.025);
    border: 1px solid rgba(0,212,255,0.06);
    margin-bottom: 6px;
    transition: all 0.3s;
}
.ov-item:hover { border-color: rgba(0,212,255,0.2); background: rgba(0,212,255,0.05); }
.ov-icon {
    width: 34px; height: 34px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 17px;
    background: rgba(0,212,255,0.07); border: 1px solid rgba(0,212,255,0.15);
}
.ov-label { font-family:'Exo 2',sans-serif; font-weight:600; font-size:13px; color:#fff; }
.ov-status { font-family:'Share Tech Mono',monospace; font-size:11px; }

/* Feed items */
.fi {
    display: flex; align-items: flex-start; gap: 9px;
    padding: 9px 11px; border-radius: 8px;
    background: rgba(0,212,255,0.015);
    border-left: 3px solid rgba(0,212,255,0.3);
    margin-bottom: 7px;
    font-family: 'Exo 2', sans-serif;
    animation: slide-in 0.5s ease-out forwards;
    opacity: 0;
}
.fi:nth-child(2){animation-delay:0.1s} .fi:nth-child(3){animation-delay:0.2s}
.fi:nth-child(4){animation-delay:0.3s} .fi:nth-child(5){animation-delay:0.4s}
.fi-live { border-left-color: var(--green); }
.fi-text { font-size:13px; color:var(--text-1); line-height:1.3; }
.fi-sub { font-size:11px; color:var(--text-2); }
@keyframes slide-in { from{opacity:0;transform:translateX(15px)} to{opacity:1;transform:translateX(0)} }

.live-tag {
    background: rgba(255,58,58,0.12); color: #ff5555;
    font-family: 'Exo 2',sans-serif; font-weight:700; font-size:10px;
    letter-spacing: 1.5px; padding: 2px 8px; border-radius: 4px;
    border: 1px solid rgba(255,58,58,0.25);
    animation: pulse-d 1.5s ease-in-out infinite;
}

/* Streamlit metric override */
[data-testid="stMetric"] {
    background: rgba(0,212,255,0.03) !important;
    border: 1px solid rgba(0,212,255,0.1) !important;
    border-radius: 8px !important;
    padding: 10px !important;
}
[data-testid="stMetricLabel"] { font-family:'Exo 2',sans-serif !important; letter-spacing:0.5px !important; }
[data-testid="stMetricValue"] { font-family:'Exo 2',sans-serif !important; color:var(--cyan) !important; font-size:18px !important; }

/* Plotly transparent */
.js-plotly-plot .plotly .main-svg { background: transparent !important; }

/* Info boxes */
[data-testid="stAlert"] {
    background: rgba(0,212,255,0.04) !important;
    border: 1px solid rgba(0,212,255,0.15) !important;
    color: var(--text-1) !important; border-radius: 8px !important;
}

hr { border-color: rgba(0,212,255,0.08) !important; }

/* Quick command button style */
.qc-btn {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; border-radius: 8px;
    background: rgba(0,212,255,0.03); border: 1px solid rgba(0,212,255,0.1);
    margin-bottom: 6px; cursor: pointer; transition: all 0.3s;
    font-family: 'Exo 2',sans-serif; font-size: 13px; color: var(--text-1);
}
.qc-btn:hover { background: rgba(0,212,255,0.08); border-color: rgba(0,212,255,0.25); }
.qc-icon { color: var(--cyan); font-size: 16px; }
</style>
""", unsafe_allow_html=True)

# Scanning line + fade-in animations
st.markdown(scanning_line_css(), unsafe_allow_html=True)


# ── Data layer ───────────────────────────────────────────────────────────────

def _get_repo():
    from friday.storage.db import get_connection
    from friday.storage.metrics_repo import MetricsRepository
    db_path = os.environ.get("DB_PATH", _DEFAULT_DB)
    conn = get_connection(db_path)
    return MetricsRepository(conn)


repo = _get_repo()
now = datetime.now(timezone.utc)
now_local = datetime.now()


def _latest(src: str, name: str) -> float | None:
    p = repo.latest(src, name)
    return p.value if p else None


def _series(src: str, name: str, hours: int = 1):
    start = now - timedelta(hours=hours)
    pts = repo.query(source=src, name=name, start=start, limit=5000)
    pts.reverse()
    return [p.timestamp for p in pts], [p.value for p in pts]


def _services_status(source: str):
    """Último estado por servicio de un source: [(servicio, health, cpu, mem)]."""
    start = now - timedelta(minutes=15)
    pts = repo.query(source=source, start=start, limit=5000)
    by: dict[str, dict] = {}
    for p in pts:  # orden desc → primero por (service,name) es el más reciente
        svc = p.service or "unknown"
        by.setdefault(svc, {}).setdefault(p.name, p)
    out = []
    for svc in sorted(by):
        m = by[svc]
        sp = m.get("status")
        health = (sp.tags or {}).get("health", "UNKNOWN") if sp else "UNKNOWN"
        cpu_v = m["cpu_percent"].value if "cpu_percent" in m else None
        mem_v = m["mem_percent"].value if "mem_percent" in m else None
        out.append((svc, health, cpu_v, mem_v))
    return out


def _sys_status(cpu, ram, disk):
    vals = [v for v in (cpu, ram, disk) if v is not None]
    if not vals:
        return "offline", "s-crit", "dot-r"
    worst = max(vals)
    if worst < 70:
        return "optimal", "s-ok", "dot-g"
    if worst < 90:
        return "degraded", "s-warn", "dot-o"
    return "critical", "s-crit", "dot-r"


def _uptime_str(s):
    if s is None: return "N/A"
    h = int(s // 3600); m = int((s % 3600) // 60)
    return f"{h//24}d {h%24}h {m}m" if h >= 24 else f"{h}h {m}m"


# ── Fetch metrics ────────────────────────────────────────────────────────────

cpu = _latest("system", "cpu_percent")
ram = _latest("system", "ram_percent")
disk = _latest("system", "disk_percent")
uptime = _latest("system", "uptime_seconds")
status_lbl, status_cls, dot_cls = _sys_status(cpu, ram, disk)

gem_req = _latest("gemini", "requests")
gem_tin = _latest("gemini", "tokens_in")
gem_tout = _latest("gemini", "tokens_out")
gem_cost = _latest("gemini", "cost_usd")

_HEALTHY = {"UP", "healthy"}
nx_services = _services_status("nexcourt")
nx_up = len(nx_services) > 0
nx_healthy = sum(1 for _, h, _, _ in nx_services if h in _HEALTHY)

ax_services = _services_status("axis")
ax_up = len(ax_services) > 0
ax_healthy = sum(1 for _, h, _, _ in ax_services if h in _HEALTHY)


# ── Estado real de subsistemas (brain / API / provider) ──────────────────────

import httpx  # noqa: E402

from friday.config import settings  # noqa: E402

_API_BASE = "http://127.0.0.1:8000/api"


@st.cache_data(ttl=4, show_spinner=False)
def _ollama_alive() -> bool:
    try:
        url = f"{settings.ollama_host.rstrip('/')}/api/tags"
        return httpx.get(url, timeout=1.0).status_code == 200
    except Exception:
        return False


@st.cache_data(ttl=4, show_spinner=False)
def _api_alive() -> bool:
    try:
        return httpx.get(f"{_API_BASE}/status", timeout=1.5).status_code == 200
    except Exception:
        return False


_provider = (settings.llm_provider or "ollama").lower()
_ollama_up = _ollama_alive()
_gem_ok = bool(settings.gemini_api_key)
_brain_up = _ollama_up if _provider == "ollama" else _gem_ok
_api_up = _api_alive()


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:24px 0 6px;">
        <div style="font-family:'Exo 2',sans-serif;font-size:26px;font-weight:900;
                    letter-spacing:8px;background:linear-gradient(180deg,#fff,#00d4ff);
                    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                    filter:drop-shadow(0 0 20px rgba(0,212,255,0.4));">FRIDAY</div>
        <div style="font-family:'Exo 2',sans-serif;font-size:10px;letter-spacing:3px;
                    color:#7a8ba0;text-transform:uppercase;margin-top:2px;">Command Center</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # Status vivo (no links de navegación falsos)
    _brain_txt = (f"{settings.ollama_model}" if _provider == "ollama"
                  else "Gemini") + (" · online" if _brain_up else " · offline")
    _live = [
        ("🧠", "AI Brain", _brain_txt, "#00ff88" if _brain_up else "#ff5555"),
        ("🌐", "API REST", "online" if _api_up else "offline",
         "#00ff88" if _api_up else "#ff5555"),
        ("🏗️", "NEXCOURT", f"{nx_healthy}/{len(nx_services)} UP" if nx_up else "sin datos",
         "#00ff88" if nx_up and nx_healthy == len(nx_services) else "#ff8c00" if nx_up else "#7a8ba0"),
        ("🖥️", "AXIS", f"{ax_healthy}/{len(ax_services)} UP" if ax_up else "sin datos",
         "#00ff88" if ax_up and ax_healthy == len(ax_services) else "#ff8c00" if ax_up else "#7a8ba0"),
    ]
    for icon, label, val, col in _live:
        st.markdown(f"""<div class="ov-item">
            <span style="font-size:15px">{icon}</span>
            <div><div class="ov-label" style="font-size:12px;">{label}</div>
            <div style="font-family:'Share Tech Mono',monospace;font-size:10px;color:{col};">{val}</div></div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # Voice status — waveform decorativo compacto (el visualizer real va abajo).
    st.markdown("""
    <div class="fc" style="padding:14px;">
        <div class="fc-title">Voice Status</div>
    </div>
    """, unsafe_allow_html=True)
    stc.html(voice_waveform_html(50, 35), height=60)
    st.markdown("""
    <div style="text-align:center;margin-top:-4px;">
        <div style="font-family:'Share Tech Mono',monospace;font-size:10px;color:#7a8ba0;">
            mic en vivo + estado en Voice ↓</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # System status
    st.markdown(f"""
    <div class="fc" style="padding:14px;">
        <div class="fc-title">System Status</div>
        <div style="display:flex;align-items:center;gap:8px;">
            <span class="dot {dot_cls}"></span>
            <span class="s-badge {status_cls}">{status_lbl}</span>
        </div>
        <div style="margin-top:10px;font-family:'Share Tech Mono',monospace;font-size:11px;color:#7a8ba0;">
            Uptime: {_uptime_str(uptime)}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Top bar ──────────────────────────────────────────────────────────────────

days_es = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
months_es = ["","enero","febrero","marzo","abril","mayo","junio",
             "julio","agosto","septiembre","octubre","noviembre","diciembre"]
day_name = days_es[now_local.weekday()]
date_str = f"{day_name}, {now_local.day} de {months_es[now_local.month]} de {now_local.year}"
time_str = now_local.strftime("%I:%M:%S %p").lstrip("0").lower().replace("am","a. m.").replace("pm","p. m.")

t1, t2, t3 = st.columns([2, 3, 2])
with t1:
    st.markdown(f"""<div style="display:flex;align-items:center;gap:12px;padding:4px 0;">
        <span style="font-family:'Exo 2',sans-serif;font-weight:700;font-size:12px;
                     letter-spacing:2px;color:#e0e6ed;">SYSTEM STATUS</span>
        <span class="s-badge {status_cls}"><span class="dot {dot_cls}"></span> {status_lbl}</span>
    </div>""", unsafe_allow_html=True)
with t2:
    st.markdown(f"""<div style="text-align:center;">
        <div style="font-family:'Exo 2',sans-serif;font-size:13px;color:#7a8ba0;letter-spacing:1px;">{date_str}</div>
        <div style="font-family:'Exo 2',sans-serif;font-size:26px;font-weight:700;color:#00d4ff;
                    text-shadow:0 0 20px rgba(0,212,255,0.4);">{time_str}</div>
    </div>""", unsafe_allow_html=True)
with t3:
    st.markdown("""<div style="text-align:right;padding:8px 0;">
        <span style="font-family:'Share Tech Mono',monospace;font-size:12px;color:#7a8ba0;">
            Gonzalo · Commander</span>
    </div>""", unsafe_allow_html=True)

st.markdown("<hr style='margin:6px 0 14px;'>", unsafe_allow_html=True)


# ── Row 1: AI Core Overview | FRIDAY Orb | Live Feed ────────────────────────

c_ov, c_orb, c_feed = st.columns([1.1, 2.2, 1.2])

with c_ov:
    st.markdown('<div class="fc friday-card-animated">', unsafe_allow_html=True)
    st.markdown('<div class="fc-title">AI Core Overview</div>', unsafe_allow_html=True)

    subsystems = [
        ("🧠", f"AI Brain ({_provider})", _brain_up),
        ("🌐", "API REST", _api_up),
        ("📡", "Collectors", cpu is not None),
        ("🏗️", "NEXCOURT", nx_up),
        ("🖥️", "AXIS", ax_up),
        ("💾", "Storage (SQLite)", True),
    ]
    for icon, name, on in subsystems:
        col = "#00ff88" if on else "#ff8c00"
        txt = "Online" if on else "Standby"
        st.markdown(f"""<div class="ov-item">
            <div class="ov-icon">{icon}</div>
            <div><div class="ov-label">{name}</div>
            <div class="ov-status" style="color:{col};">{txt}</div></div>
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

with c_orb:
    stc.html(friday_orb_html(400), height=420)

with c_feed:
    st.markdown('<div class="fc friday-card-animated">', unsafe_allow_html=True)
    st.markdown('<div class="fc-title">Live Intelligence Feed <span class="live-tag">LIVE</span></div>',
                unsafe_allow_html=True)

    feed = []
    if cpu is not None:
        lvl = "nominal" if cpu < 70 else "elevated" if cpu < 90 else "critical"
        feed.append(("📈", f"CPU at {cpu:.0f}%", f"System load {lvl}", True))
    if ram is not None:
        feed.append(("🧠", f"RAM at {ram:.0f}%", "Memory tracking active", True))
    if disk is not None:
        feed.append(("💾", f"Disk at {disk:.0f}%", "Storage monitoring", True))
    if gem_cost is not None and gem_cost > 0:
        feed.append(("💰", f"Gemini: ${gem_cost:.4f}", "Last cycle cost", True))
    if not feed:
        feed.append(("⏳", "Waiting for data...", "Start collectors", False))
    if nx_up:
        feed.append(("🏗️", f"NEXCOURT: {nx_healthy}/{len(nx_services)} UP",
                     "ECS · CloudWatch", nx_healthy == len(nx_services)))
    else:
        feed.append(("🏗️", "NEXCOURT not linked", "Configure .env to enable", False))

    for icon, text, sub, live in feed[:6]:
        lc = "fi-live" if live else ""
        st.markdown(f"""<div class="fi {lc}">
            <span style="font-size:15px;">{icon}</span>
            <div><div class="fi-text">{text}</div><div class="fi-sub">{sub}</div></div>
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ── Row 2: Active Subsystems | Quick Commands ───────────────────────────────

c_agents, c_timeline, c_qc = st.columns([1.6, 1.2, 1])

with c_agents:
    st.markdown('<div class="fc friday-card-scan friday-card-animated">', unsafe_allow_html=True)
    st.markdown('<div class="fc-title">Active Subsystems</div>', unsafe_allow_html=True)

    agents = [
        ("🧠", "AI Brain", _brain_up),
        ("📡", "System Collector", cpu is not None),
        ("🏗️", "NEXCOURT", nx_up),
        ("🖥️", "AXIS", ax_up),
        ("💰", "Gemini Tracker", _gem_ok),
        ("🌐", "API REST", _api_up),
    ]

    cols_html = '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">'
    for icon, name, active in agents:
        bg = "rgba(0,255,136,0.04)" if active else "rgba(255,140,0,0.03)"
        bc = "rgba(0,255,136,0.15)" if active else "rgba(255,140,0,0.1)"
        dc = "dot-g" if active else "dot-o"
        s = "Active" if active else "Standby"
        sc = "#00ff88" if active else "#ff8c00"
        cols_html += f"""<div style="background:{bg};border:1px solid {bc};border-radius:10px;
                         padding:12px;text-align:center;">
            <div style="font-size:24px;margin-bottom:6px;">{icon}</div>
            <div style="font-family:'Exo 2',sans-serif;font-weight:600;font-size:12px;color:#fff;">{name}</div>
            <div style="display:flex;align-items:center;justify-content:center;gap:5px;margin-top:4px;">
                <span class="dot {dc}" style="width:6px;height:6px;"></span>
                <span style="font-family:'Share Tech Mono',monospace;font-size:10px;color:{sc};">{s}</span>
            </div>
        </div>"""
    cols_html += '</div>'
    st.markdown(cols_html, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with c_timeline:
    st.markdown('<div class="fc friday-card-animated">', unsafe_allow_html=True)
    st.markdown('<div class="fc-title">Metrics Timeline</div>', unsafe_allow_html=True)

    ts_cpu, vals_cpu = _series("system", "cpu_percent")
    if ts_cpu:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ts_cpu, y=vals_cpu, mode="lines",
            line=dict(color="#00d4ff", width=2), fill="tozeroy",
            fillcolor="rgba(0,212,255,0.06)"))
        fig.update_layout(height=180, margin=dict(t=10,b=25,l=35,r=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, color="#7a8ba0", type="date"),
            yaxis=dict(showgrid=True, gridcolor="rgba(0,212,255,0.04)", color="#7a8ba0"),
            font=dict(family="Share Tech Mono", size=9))
        st.plotly_chart(fig, width="stretch")
    else:
        st.markdown("""<div style="text-align:center;padding:40px 0;color:#7a8ba0;
                    font-family:'Exo 2',sans-serif;">No timeline data yet</div>""",
                    unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

with c_qc:
    st.markdown('<div class="fc friday-card-animated">', unsafe_allow_html=True)
    st.markdown('<div class="fc-title">Quick Commands</div>', unsafe_allow_html=True)

    # Botones reales: encolan una pregunta al chat de FRIDAY (más abajo).
    _quick = [
        ("🏗️ Estado NEXCOURT", "¿Cómo están los servicios de NEXCOURT ahora mismo?"),
        ("🖥️ Estado AXIS", "¿Cómo están los containers de AXIS?"),
        ("🚨 Errores recientes", "¿Hay errores recientes en algún servicio?"),
        ("💰 Resumen de costos", "Dame el resumen de costos de Gemini de hoy."),
    ]
    for label, question in _quick:
        if st.button(label, key=f"qc_{label}", use_container_width=True):
            st.session_state.pending_prompt = question
            st.rerun()
    if st.button("🔄 Refrescar datos", key="qc_refresh", use_container_width=True):
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# ── Row 3: System Monitor | Gemini Usage | LLM Status ───────────────────────

c_sys, c_gem, c_llm = st.columns([1.2, 1.6, 0.9])


def _donut(val, label, max_v=100):
    v = val if val is not None else 0
    color = "#00ff88" if v < 60 else "#ff8c00" if v < 85 else "#ff3a3a"
    fig = go.Figure(go.Pie(
        values=[v, max_v - v], hole=0.78,
        marker=dict(colors=[color, "rgba(255,255,255,0.02)"], line=dict(width=0)),
        textinfo="none", hoverinfo="none", sort=False, direction="clockwise", rotation=90))
    fig.add_annotation(text=f"<b>{label}</b>", x=0.5, y=0.6, showarrow=False,
        font=dict(family="Exo 2", size=12, color="#7a8ba0"))
    fig.add_annotation(text=f"<b>{v:.0f}%</b>", x=0.5, y=0.4, showarrow=False,
        font=dict(family="Exo 2", size=18, color=color))
    fig.update_layout(showlegend=False, height=160, width=160,
        margin=dict(t=8,b=8,l=8,r=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


with c_sys:
    st.markdown('<div class="fc friday-card-scan friday-card-animated">', unsafe_allow_html=True)
    st.markdown('<div class="fc-title">System Monitor</div>', unsafe_allow_html=True)

    g1, g2, g3 = st.columns(3)
    with g1:
        st.plotly_chart(_donut(cpu, "CPU"), width="stretch")
    with g2:
        st.plotly_chart(_donut(ram, "RAM"), width="stretch")
    with g3:
        st.plotly_chart(_donut(disk, "Disk"), width="stretch")

    st.markdown('</div>', unsafe_allow_html=True)

with c_gem:
    st.markdown('<div class="fc friday-card-animated">', unsafe_allow_html=True)
    st.markdown('<div class="fc-title">Gemini Usage</div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Requests", f"{int(gem_req)}" if gem_req else "0")
    with m2:
        st.metric("Tokens In", f"{int(gem_tin):,}" if gem_tin else "0")
    with m3:
        st.metric("Tokens Out", f"{int(gem_tout):,}" if gem_tout else "0")
    with m4:
        st.metric("Cost USD", f"${gem_cost:.4f}" if gem_cost else "$0.00")

    ts_c, vs_c = _series("gemini", "cost_usd", hours=24)
    if ts_c:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=ts_c, y=vs_c, mode="lines", fill="tozeroy",
            line=dict(color="#00d4ff", width=2), fillcolor="rgba(0,212,255,0.08)"))
        fig.update_layout(height=130, margin=dict(t=8,b=25,l=35,r=10),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, color="#7a8ba0", type="date"),
            yaxis=dict(showgrid=True, gridcolor="rgba(0,212,255,0.04)", color="#7a8ba0"),
            font=dict(family="Share Tech Mono", size=9))
        st.plotly_chart(fig, width="stretch")

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cost_today = sum(p.value for p in repo.query(source="gemini", name="cost_usd", start=today_start, limit=10000))
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cost_month = sum(p.value for p in repo.query(source="gemini", name="cost_usd", start=month_start, limit=50000))
    ac1, ac2 = st.columns(2)
    with ac1:
        st.metric("Hoy", f"${cost_today:.4f}")
    with ac2:
        st.metric("Este mes", f"${cost_month:.4f}")

    st.markdown('</div>', unsafe_allow_html=True)

with c_llm:
    st.markdown('<div class="fc friday-card-animated">', unsafe_allow_html=True)
    st.markdown('<div class="fc-title">LLM Status</div>', unsafe_allow_html=True)

    if _provider == "ollama":
        providers = [
            ("🟢" if _ollama_up else "🔴", f"Ollama · {settings.ollama_model}",
             "Connected (local)" if _ollama_up else "Offline",
             "#00ff88" if _ollama_up else "#ff5555"),
            ("🟢" if _gem_ok else "⚪", "Gemini",
             "Available" if _gem_ok else "Not configured", "#7a8ba0"),
        ]
    else:
        providers = [
            ("🟢" if _gem_ok else "⚪", "Gemini",
             "Connected" if _gem_ok else "No key",
             "#00ff88" if _gem_ok else "#7a8ba0"),
            ("🟢" if _ollama_up else "⚪", "Ollama (local)",
             "Available" if _ollama_up else "Offline", "#7a8ba0"),
        ]
    for icon, name, status, color in providers:
        st.markdown(f"""<div class="ov-item">
            <span style="font-size:13px;">{icon}</span>
            <div><div class="ov-label" style="font-size:12px;">{name}</div>
            <div style="font-family:'Share Tech Mono',monospace;font-size:10px;color:{color};">{status}</div></div>
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ── Paneles de sistemas (NEXCOURT · AXIS) ────────────────────────────────────

def _system_panel(title, services, healthy, up, hint):
    st.markdown('<div class="fc friday-card-animated">', unsafe_allow_html=True)
    total = len(services)
    badge = (f'<span class="s-badge s-ok">{healthy}/{total} UP</span>'
             if up and healthy == total
             else f'<span class="s-badge s-warn">{healthy}/{total} UP</span>'
             if up else '<span class="s-badge s-crit">offline</span>')
    st.markdown(f'<div class="fc-title">{title} {badge}</div>', unsafe_allow_html=True)

    if up:
        grid = '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;">'
        for svc, health, cpu_v, mem_v in services:
            ok = health in _HEALTHY
            bg = "rgba(0,255,136,0.04)" if ok else "rgba(255,58,58,0.04)"
            bc = "rgba(0,255,136,0.15)" if ok else "rgba(255,58,58,0.2)"
            dc = "dot-g" if ok else "dot-r"
            sc = "#00ff88" if ok else "#ff5555"
            cpu_s = f"{cpu_v:.1f}%" if cpu_v is not None else "—"
            mem_s = f"{mem_v:.1f}%" if mem_v is not None else "—"
            name = svc.replace("-service", "").replace("axis-", "")
            grid += f"""<div style="background:{bg};border:1px solid {bc};border-radius:10px;padding:12px;">
                <div style="display:flex;align-items:center;justify-content:space-between;">
                    <span style="font-family:'Exo 2',sans-serif;font-weight:600;font-size:13px;color:#fff;">{name}</span>
                    <span class="dot {dc}" style="width:7px;height:7px;"></span>
                </div>
                <div style="display:flex;gap:14px;margin-top:8px;font-family:'Share Tech Mono',monospace;font-size:11px;">
                    <span style="color:#7a8ba0;">CPU <span style="color:{sc};">{cpu_s}</span></span>
                    <span style="color:#7a8ba0;">MEM <span style="color:{sc};">{mem_s}</span></span>
                </div>
            </div>"""
        grid += '</div>'
        st.markdown(grid, unsafe_allow_html=True)
    else:
        st.markdown(f"""<div style="text-align:center;padding:30px 0;color:#7a8ba0;font-family:'Exo 2',sans-serif;">
            {hint}</div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


_system_panel("🏗️ NEXCOURT · AWS ECS", nx_services, nx_healthy, nx_up,
              "NEXCOURT sin datos · activá <code>nexcourt_mode=cloudwatch</code> en .env")
_system_panel("🖥️ AXIS · Docker (droplet)", ax_services, ax_healthy, ax_up,
              "AXIS sin datos · activá <code>axis_enabled=true</code> en .env")


# ── Live Voice + Tool Transparency ──────────────────────────────────────────
# Todo HTML+JS puro: fetch cada 1s a la API, sin rerun de Streamlit.
#  • Mic visualizer: barras que reaccionan a TU voz real (Web Audio del navegador).
#  • Voice Activity: transcripción/respuestas del listener.
#  • Tool Activity: qué tools ejecuta FRIDAY en vivo → delata alucinaciones.

st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
st.markdown("#### 🎙️ Live Voice")
st.markdown(
    '<div style="font-size:10px;color:#555;margin-bottom:6px;">'
    'El micrófono reacciona a tu voz en tiempo real (permití el acceso al mic). '
    'Estado y actividad se actualizan cada 1s.</div>',
    unsafe_allow_html=True,
)
stc.html(live_mic_visualizer_html(150), height=210)

v_left, v_right = st.columns(2)
with v_left:
    st.markdown('<div class="fc-title">🎤 Voice Activity</div>', unsafe_allow_html=True)
    stc.html(voice_log_html(300), height=320)
with v_right:
    st.markdown(
        '<div class="fc-title">🔧 Tool Activity '
        '<span class="live-tag">LIVE</span></div>',
        unsafe_allow_html=True,
    )
    stc.html(tool_activity_html(300), height=320)


# ── Chat interactivo con FRIDAY (POST /api/chat) ─────────────────────────────

st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
st.markdown("#### 💬 Hablá con FRIDAY")


@st.cache_data(ttl=5, show_spinner=False)
def _fetch_sessions() -> list[dict]:
    try:
        r = httpx.get(f"{_API_BASE}/chat/sessions", timeout=3)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


def _fetch_messages(session_id: str) -> list[dict]:
    try:
        r = httpx.get(f"{_API_BASE}/chat/sessions/{session_id}", timeout=5)
        return r.json().get("messages", []) if r.status_code == 200 else []
    except Exception:
        return []


def _send_chat(message: str, model: str = "auto") -> str:
    r = httpx.post(f"{_API_BASE}/chat",
                   json={"message": message, "model": model}, timeout=180)
    r.raise_for_status()
    return r.json().get("response", "(sin respuesta)")


_sessions = _fetch_sessions()

# Sembrar la conversación activa (la más reciente) una vez por carga de página.
if "chat_history" not in st.session_state:
    if _sessions:
        st.session_state.chat_history = [
            (m["role"], m["content"]) for m in _fetch_messages(_sessions[0]["id"])
        ]
    else:
        st.session_state.chat_history = []

if not _brain_up:
    st.warning("⚠️ El cerebro está offline (Ollama caído o sin API key). "
               "Levantá FRIDAY para poder chatear.")
elif not _api_up:
    st.warning("⚠️ La API de FRIDAY no responde en :8000. ¿Está corriendo `friday.app`?")

for _role, _content in st.session_state.chat_history[-20:]:
    with st.chat_message("user" if _role == "user" else "assistant",
                         avatar="🧑" if _role == "user" else "🤖"):
        st.markdown(_content)

# Selector de modelo solo con Gemini (en Ollama el modelo es fijo).
_model = "auto"
if _provider == "gemini":
    _model = st.radio("Modelo", ["auto", "flash", "pro"], horizontal=True, key="chat_model")

# El prompt viene del input o de un Quick Command encolado.
_pending = st.session_state.pop("pending_prompt", None)
_typed = st.chat_input("Preguntale por NEXCOURT, AXIS, costos, errores…",
                       disabled=not (_brain_up and _api_up))
_prompt = _typed or _pending

if _prompt:
    st.session_state.chat_history.append(("user", _prompt))
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("FRIDAY está pensando…"):
            try:
                _answer = _send_chat(_prompt, _model)
            except Exception as exc:
                _answer = f"⚠️ No pude contactar a FRIDAY: {exc}"
    st.session_state.chat_history.append(("assistant", _answer))
    st.rerun()

with st.expander("📜 Historial de sesiones anteriores"):
    if _sessions:
        _labels = {
            s["id"]: f"{s.get('title') or 'Chat'} — {str(s.get('created_at', ''))[:16].replace('T', ' ')}"
            for s in _sessions
        }
        _sel = st.selectbox("Sesión", options=list(_labels.keys()),
                            format_func=lambda x: _labels[x], key="hist_sel")
        if _sel:
            for m in _fetch_messages(_sel):
                _who = "🧑 Vos" if m["role"] == "user" else "🤖 FRIDAY"
                st.markdown(f"**{_who}:** {m['content']}")
    else:
        st.caption("Todavía no hay conversaciones.")


# ── Auto-refresco ────────────────────────────────────────────────────────────
# Relajado a 15s: las secciones críticas usan @st.fragment con su propio ritmo.

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=15_000, key="friday_refresh")
except ImportError:
    pass
