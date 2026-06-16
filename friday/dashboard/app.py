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
    scanning_line_css,
    talk_bar_html,
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

    for icon, label in [("🏠","Command Center"),("🧠","AI Core"),("📊","Métricas"),
                        ("🔧","Sistema"),("💰","Costos"),("🏗️","NEXCOURT"),("⚡","Acciones"),("📋","Tasks")]:
        st.markdown(f'<div class="ov-item" style="cursor:pointer"><span style="font-size:16px">{icon}</span>'
                    f'<span class="ov-label">{label}</span></div>', unsafe_allow_html=True)

    st.markdown("---")

    # Voice status
    st.markdown("""
    <div class="fc" style="padding:14px;">
        <div class="fc-title">Voice Status</div>
    </div>
    """, unsafe_allow_html=True)
    stc.html(voice_waveform_html(50, 35), height=60)
    st.markdown("""
    <div style="text-align:center;margin-top:-4px;">
        <div style="font-family:'Share Tech Mono',monospace;font-size:11px;color:#00d4ff;
                    animation:pulse-d 2s ease-in-out infinite;">Listening...</div>
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
        ("🧠", "AI Core (Gemini)", gem_req is not None),
        ("💾", "Memory / Storage", True),
        ("📡", "Collectors", cpu is not None),
        ("🏗️", "NEXCOURT", False),
        ("📊", "Dashboard", True),
        ("🔧", "System", cpu is not None),
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
        ("📡", "System Collector", cpu is not None),
        ("💰", "Gemini Tracker", True),
        ("🏗️", "NEXCOURT Collector", False),
        ("📊", "Dashboard Server", True),
        ("🧠", "AI Brain", False),
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

    for icon, label in [("➕","Start New Task"),("📊","View Metrics"),("🔄","Refresh Data"),
                        ("🧠","Ask FRIDAY"),("▶️","Run Workflow")]:
        st.markdown(f"""<div class="qc-btn">
            <span class="qc-icon">{icon}</span><span>{label}</span>
        </div>""", unsafe_allow_html=True)

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

    providers = [
        ("🟢", "Gemini", "Connected", "#00ff88"),
        ("⚪", "Claude Code", "Not Linked", "#7a8ba0"),
        ("⚪", "NEXCOURT API", "Not Linked", "#7a8ba0"),
    ]
    for icon, name, status, color in providers:
        st.markdown(f"""<div class="ov-item">
            <span style="font-size:13px;">{icon}</span>
            <div><div class="ov-label" style="font-size:12px;">{name}</div>
            <div style="font-family:'Share Tech Mono',monospace;font-size:10px;color:{color};">{status}</div></div>
        </div>""", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ── Bottom: TALK TO FRIDAY ──────────────────────────────────────────────────

st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
stc.html(talk_bar_html(70), height=80)


# ── Auto-refresco ────────────────────────────────────────────────────────────

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=10_000, key="friday_refresh")
except ImportError:
    pass
