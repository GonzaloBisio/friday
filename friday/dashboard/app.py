"""FRIDAY Dashboard — Panel de control futurista estilo comando central."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB = str(_PROJECT_ROOT / "friday.db")

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="FRIDAY — Command Center",
    page_icon="🔷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@300;400;500;600;700&family=Share+Tech+Mono&display=swap');

:root {
    --bg-primary: #0a0e17;
    --bg-secondary: #0d1321;
    --bg-card: #111827;
    --border-glow: #00d4ff;
    --accent-cyan: #00d4ff;
    --accent-teal: #00ffc8;
    --accent-orange: #ff8c00;
    --accent-red: #ff3a3a;
    --accent-green: #00ff88;
    --text-primary: #e0e6ed;
    --text-secondary: #7a8ba0;
    --text-bright: #ffffff;
}

/* Main background */
.stApp, [data-testid="stAppViewContainer"], .main .block-container {
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

header[data-testid="stHeader"] {
    background-color: var(--bg-primary) !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b1023 0%, #0a0e17 100%) !important;
    border-right: 1px solid rgba(0, 212, 255, 0.15) !important;
}

[data-testid="stSidebar"] * {
    color: var(--text-primary) !important;
}

/* Card panels */
.friday-card {
    background: linear-gradient(135deg, rgba(17, 24, 39, 0.95) 0%, rgba(13, 19, 33, 0.95) 100%);
    border: 1px solid rgba(0, 212, 255, 0.2);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 0 15px rgba(0, 212, 255, 0.05), inset 0 1px 0 rgba(0, 212, 255, 0.1);
    position: relative;
    overflow: hidden;
}

.friday-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
}

.friday-card-title {
    font-family: 'Rajdhani', sans-serif;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: var(--accent-cyan);
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(0, 212, 255, 0.1);
}

/* Status badges */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-family: 'Rajdhani', sans-serif;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

.status-optimal {
    background: rgba(0, 255, 136, 0.1);
    border: 1px solid rgba(0, 255, 136, 0.3);
    color: var(--accent-green);
}

.status-degraded {
    background: rgba(255, 140, 0, 0.1);
    border: 1px solid rgba(255, 140, 0, 0.3);
    color: var(--accent-orange);
}

.status-critical {
    background: rgba(255, 58, 58, 0.1);
    border: 1px solid rgba(255, 58, 58, 0.3);
    color: var(--accent-red);
}

.status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
    animation: pulse-dot 2s ease-in-out infinite;
}

.dot-green { background: var(--accent-green); box-shadow: 0 0 6px var(--accent-green); }
.dot-orange { background: var(--accent-orange); box-shadow: 0 0 6px var(--accent-orange); }
.dot-red { background: var(--accent-red); box-shadow: 0 0 6px var(--accent-red); }
.dot-cyan { background: var(--accent-cyan); box-shadow: 0 0 6px var(--accent-cyan); }

@keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

/* Hero section */
.friday-hero {
    text-align: center;
    padding: 30px 20px;
    background: radial-gradient(ellipse at center, rgba(0, 212, 255, 0.08) 0%, transparent 70%);
    border: 1px solid rgba(0, 212, 255, 0.15);
    border-radius: 16px;
    margin-bottom: 16px;
    position: relative;
}

.friday-hero-title {
    font-family: 'Orbitron', monospace;
    font-weight: 900;
    font-size: 48px;
    letter-spacing: 18px;
    background: linear-gradient(180deg, #ffffff 0%, #00d4ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-shadow: 0 0 40px rgba(0, 212, 255, 0.3);
    margin: 0;
}

.friday-hero-subtitle {
    font-family: 'Rajdhani', sans-serif;
    font-weight: 400;
    font-size: 16px;
    letter-spacing: 6px;
    color: var(--accent-cyan);
    margin-top: 4px;
    opacity: 0.8;
}

.friday-hero-version {
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px;
    color: var(--text-secondary);
    margin-top: 8px;
}

/* Top bar */
.top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    margin-bottom: 16px;
    border-bottom: 1px solid rgba(0, 212, 255, 0.1);
}

.top-bar-time {
    font-family: 'Orbitron', monospace;
    font-size: 28px;
    font-weight: 700;
    color: var(--accent-cyan);
    text-shadow: 0 0 20px rgba(0, 212, 255, 0.4);
}

.top-bar-date {
    font-family: 'Rajdhani', sans-serif;
    font-size: 14px;
    color: var(--text-secondary);
    letter-spacing: 1px;
}

/* Overview items */
.overview-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    border-radius: 8px;
    background: rgba(0, 212, 255, 0.03);
    border: 1px solid rgba(0, 212, 255, 0.08);
    margin-bottom: 8px;
    transition: border-color 0.3s;
}

.overview-item:hover {
    border-color: rgba(0, 212, 255, 0.25);
}

.overview-icon {
    width: 36px; height: 36px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    background: rgba(0, 212, 255, 0.1);
    border: 1px solid rgba(0, 212, 255, 0.2);
}

.overview-label {
    font-family: 'Rajdhani', sans-serif;
    font-weight: 600;
    font-size: 14px;
    color: var(--text-bright);
}

.overview-status {
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
}

/* Live feed */
.feed-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    background: rgba(0, 212, 255, 0.02);
    border-left: 3px solid var(--accent-cyan);
    margin-bottom: 8px;
    font-family: 'Rajdhani', sans-serif;
}

.feed-item-live {
    border-left-color: var(--accent-green);
}

.feed-text {
    font-size: 14px;
    color: var(--text-primary);
    line-height: 1.4;
}

.feed-sub {
    font-size: 12px;
    color: var(--text-secondary);
}

.live-tag {
    background: rgba(255, 58, 58, 0.15);
    color: #ff5555;
    font-family: 'Rajdhani', sans-serif;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 1.5px;
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid rgba(255, 58, 58, 0.3);
    animation: pulse-dot 1.5s ease-in-out infinite;
}

/* Metric displays */
.metric-big {
    font-family: 'Orbitron', monospace;
    font-size: 32px;
    font-weight: 700;
    color: var(--accent-cyan);
    text-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
}

.metric-label {
    font-family: 'Rajdhani', sans-serif;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-top: 4px;
}

.metric-unit {
    font-family: 'Share Tech Mono', monospace;
    font-size: 14px;
    color: var(--text-secondary);
}

/* Plotly chart backgrounds */
.js-plotly-plot .plotly .main-svg {
    background: transparent !important;
}

/* Hide default streamlit metric styling */
[data-testid="stMetric"] {
    background: rgba(0, 212, 255, 0.03) !important;
    border: 1px solid rgba(0, 212, 255, 0.1) !important;
    border-radius: 8px !important;
    padding: 12px !important;
}

[data-testid="stMetricLabel"] {
    font-family: 'Rajdhani', sans-serif !important;
    letter-spacing: 1px !important;
}

[data-testid="stMetricValue"] {
    font-family: 'Orbitron', monospace !important;
    color: var(--accent-cyan) !important;
}

/* Dividers */
hr {
    border-color: rgba(0, 212, 255, 0.1) !important;
}

/* Info boxes */
[data-testid="stAlert"] {
    background: rgba(0, 212, 255, 0.05) !important;
    border: 1px solid rgba(0, 212, 255, 0.2) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
}
</style>
""", unsafe_allow_html=True)


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


def _latest(source: str, name: str) -> float | None:
    p = repo.latest(source, name)
    return p.value if p else None


def _time_series(source: str, name: str, hours: int = 1) -> tuple[list, list]:
    start = now - timedelta(hours=hours)
    points = repo.query(source=source, name=name, start=start, limit=5000)
    points.reverse()
    return [p.timestamp for p in points], [p.value for p in points]


def _system_status(cpu, ram, disk) -> tuple[str, str, str]:
    """Determina estado global: optimal/degraded/critical."""
    vals = [v for v in (cpu, ram, disk) if v is not None]
    if not vals:
        return "offline", "critical", "dot-red"
    worst = max(vals)
    if worst < 70:
        return "optimal", "status-optimal", "dot-green"
    if worst < 90:
        return "degraded", "status-degraded", "dot-orange"
    return "critical", "status-critical", "dot-red"


def _format_uptime(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h >= 24:
        return f"{h // 24}d {h % 24}h {m}m"
    return f"{h}h {m}m"


# ── Fetch current metrics ────────────────────────────────────────────────────

cpu = _latest("system", "cpu_percent")
ram = _latest("system", "ram_percent")
disk = _latest("system", "disk_percent")
uptime = _latest("system", "uptime_seconds")
status_label, status_class, dot_class = _system_status(cpu, ram, disk)

gem_requests = _latest("gemini", "requests")
gem_tokens_in = _latest("gemini", "tokens_in")
gem_tokens_out = _latest("gemini", "tokens_out")
gem_cost = _latest("gemini", "cost_usd")


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 20px 0 10px;">
        <div style="font-family:'Orbitron',monospace; font-size:28px; font-weight:900;
                    letter-spacing:8px; background:linear-gradient(180deg,#fff,#00d4ff);
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
            FRIDAY
        </div>
        <div style="font-family:'Rajdhani',sans-serif; font-size:11px; letter-spacing:3px;
                    color:#7a8ba0; text-transform:uppercase; margin-top:2px;">
            Command Center
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    nav_items = [
        ("🏠", "Command Center"),
        ("🧠", "AI Core"),
        ("📊", "Métricas"),
        ("🔧", "Sistema"),
        ("💰", "Costos Gemini"),
        ("🏗️", "NEXCOURT"),
        ("⚡", "Acciones"),
    ]

    for icon, label in nav_items:
        st.markdown(f"""
        <div class="overview-item" style="cursor:pointer;">
            <span style="font-size:18px;">{icon}</span>
            <span class="overview-label">{label}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # System status en sidebar
    st.markdown(f"""
    <div class="friday-card" style="padding:14px;">
        <div class="friday-card-title">System Status</div>
        <div style="display:flex; align-items:center; gap:8px;">
            <span class="status-dot {dot_class}"></span>
            <span class="status-badge {status_class}">{status_label}</span>
        </div>
        <div style="margin-top:12px; font-family:'Share Tech Mono',monospace; font-size:12px; color:#7a8ba0;">
            Uptime: {_format_uptime(uptime)}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Top bar ──────────────────────────────────────────────────────────────────

days_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
months_es = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

day_name = days_es[now_local.weekday()]
date_str = f"{day_name}, {now_local.day} de {months_es[now_local.month]} de {now_local.year}"
time_str = now_local.strftime("%I:%M:%S %p").lstrip("0").lower().replace("am", "a. m.").replace("pm", "p. m.")

top1, top2, top3 = st.columns([2, 3, 2])

with top1:
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:12px; padding:4px 0;">
        <span style="font-family:'Rajdhani',sans-serif; font-weight:700; font-size:13px;
                     letter-spacing:2px; color:#e0e6ed;">SYSTEM STATUS</span>
        <span class="status-badge {status_class}">
            <span class="status-dot {dot_class}"></span> {status_label}
        </span>
    </div>
    """, unsafe_allow_html=True)

with top2:
    st.markdown(f"""
    <div style="text-align:center;">
        <div class="top-bar-date">{date_str}</div>
        <div class="top-bar-time">{time_str}</div>
    </div>
    """, unsafe_allow_html=True)

with top3:
    st.markdown(f"""
    <div style="text-align:right; padding:8px 0;">
        <span style="font-family:'Share Tech Mono',monospace; font-size:12px; color:#7a8ba0;">
            Gonzalo · Commander
        </span>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<hr style='margin:8px 0 16px;'>", unsafe_allow_html=True)


# ── Row 1: AI Core Overview | Hero | Live Intelligence Feed ─────────────────

col_overview, col_hero, col_feed = st.columns([1.2, 2, 1.3])

with col_overview:
    st.markdown("""<div class="friday-card">
        <div class="friday-card-title">AI Core Overview</div>
    """, unsafe_allow_html=True)

    subsystems = [
        ("🧠", "AI Core (Gemini)", gem_requests is not None),
        ("💾", "Storage", True),
        ("📡", "Collectors", cpu is not None),
        ("🏗️", "NEXCOURT", False),
        ("📊", "Dashboard", True),
    ]

    for icon, name, online in subsystems:
        s_color = "#00ff88" if online else "#ff8c00"
        s_text = "Online" if online else "Standby"
        st.markdown(f"""
        <div class="overview-item">
            <div class="overview-icon">{icon}</div>
            <div>
                <div class="overview-label">{name}</div>
                <div class="overview-status" style="color:{s_color};">{s_text}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

with col_hero:
    st.markdown(f"""
    <div class="friday-hero">
        <div class="friday-hero-title">F R I D A Y</div>
        <div class="friday-hero-subtitle">AI CORE</div>
        <div class="friday-hero-version">v0.1.0</div>
        <div style="margin-top:20px; font-family:'Share Tech Mono',monospace; font-size:12px; color:#7a8ba0;">
            Gemini 2.5 Pro · SQLite · {len([v for v in (cpu, ram, disk) if v is not None])} collectors activos
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_feed:
    st.markdown("""<div class="friday-card">
        <div class="friday-card-title" style="display:flex; justify-content:space-between; align-items:center;">
            Live Intelligence Feed
            <span class="live-tag">LIVE</span>
        </div>
    """, unsafe_allow_html=True)

    feed_items = []
    if cpu is not None:
        level = "nominal" if cpu < 70 else "elevated" if cpu < 90 else "critical"
        feed_items.append(("📈", f"CPU usage at {cpu:.0f}%", f"System load {level}", True))
    if ram is not None:
        feed_items.append(("🧠", f"RAM at {ram:.0f}%", f"Memory usage tracking", True))
    if gem_cost is not None and gem_cost > 0:
        feed_items.append(("💰", f"Gemini cost: ${gem_cost:.4f}", "Last collection cycle", True))
    if not feed_items:
        feed_items.append(("⏳", "Waiting for data...", "Start collectors to see live metrics", False))

    feed_items.append(("🏗️", "NEXCOURT not connected", "Configure in .env to enable", False))

    for icon, text, sub, is_live in feed_items[:5]:
        live_class = "feed-item-live" if is_live else ""
        st.markdown(f"""
        <div class="feed-item {live_class}">
            <span style="font-size:16px;">{icon}</span>
            <div>
                <div class="feed-text">{text}</div>
                <div class="feed-sub">{sub}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ── Row 2: System Monitor | Gemini Usage | LLM Status ───────────────────────

col_sys, col_gem, col_llm = st.columns([1.2, 1.5, 1])


def _circular_gauge(value: float | None, label: str, max_val: float = 100) -> go.Figure:
    val = value if value is not None else 0
    if val < 60:
        color = "#00ff88"
    elif val < 85:
        color = "#ff8c00"
    else:
        color = "#ff3a3a"

    fig = go.Figure(go.Pie(
        values=[val, max_val - val],
        hole=0.75,
        marker=dict(colors=[color, "rgba(255,255,255,0.03)"], line=dict(width=0)),
        textinfo="none",
        hoverinfo="none",
        sort=False,
        direction="clockwise",
        rotation=90,
    ))
    fig.add_annotation(
        text=f"<b>{label}</b>",
        x=0.5, y=0.58, showarrow=False,
        font=dict(family="Rajdhani", size=13, color="#7a8ba0"),
    )
    fig.add_annotation(
        text=f"<b>{val:.0f}%</b>",
        x=0.5, y=0.42, showarrow=False,
        font=dict(family="Orbitron", size=20, color=color),
    )
    fig.update_layout(
        showlegend=False,
        height=180, width=180,
        margin=dict(t=10, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


with col_sys:
    st.markdown("""<div class="friday-card">
        <div class="friday-card-title">System Monitor</div>
    """, unsafe_allow_html=True)

    g1, g2, g3 = st.columns(3)
    with g1:
        st.plotly_chart(_circular_gauge(cpu, "CPU"), width="stretch")
    with g2:
        st.plotly_chart(_circular_gauge(ram, "RAM"), width="stretch")
    with g3:
        st.plotly_chart(_circular_gauge(disk, "Disk"), width="stretch")

    st.markdown("</div>", unsafe_allow_html=True)


with col_gem:
    st.markdown("""<div class="friday-card">
        <div class="friday-card-title">Gemini Usage</div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Requests", f"{int(gem_requests)}" if gem_requests else "0")
    with m2:
        st.metric("Tokens In", f"{int(gem_tokens_in):,}" if gem_tokens_in else "0")
    with m3:
        st.metric("Tokens Out", f"{int(gem_tokens_out):,}" if gem_tokens_out else "0")
    with m4:
        st.metric("Cost", f"${gem_cost:.4f}" if gem_cost else "$0.00")

    # Cost chart
    ts_cost, vals_cost = _time_series("gemini", "cost_usd", hours=24)
    if ts_cost:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=ts_cost, y=vals_cost, mode="lines",
            fill="tozeroy",
            line=dict(color="#00d4ff", width=2),
            fillcolor="rgba(0, 212, 255, 0.1)",
        ))
        fig.update_layout(
            height=160,
            margin=dict(t=10, b=30, l=40, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, color="#7a8ba0", type="date"),
            yaxis=dict(showgrid=True, gridcolor="rgba(0,212,255,0.05)", color="#7a8ba0",
                       title=dict(text="USD", font=dict(size=10))),
            font=dict(family="Share Tech Mono", size=10),
        )
        st.plotly_chart(fig, width="stretch")

    # Acumulados
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cost_today = sum(
        p.value for p in repo.query(source="gemini", name="cost_usd", start=today_start, limit=10000)
    )
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cost_month = sum(
        p.value for p in repo.query(source="gemini", name="cost_usd", start=month_start, limit=50000)
    )

    ac1, ac2 = st.columns(2)
    with ac1:
        st.metric("Costo hoy", f"${cost_today:.4f}")
    with ac2:
        st.metric("Costo mes", f"${cost_month:.4f}")

    st.markdown("</div>", unsafe_allow_html=True)


with col_llm:
    st.markdown("""<div class="friday-card">
        <div class="friday-card-title">LLM Status</div>
    """, unsafe_allow_html=True)

    llm_providers = [
        ("🟢", "Gemini", "Connected", "#00ff88"),
        ("⚪", "NEXCOURT API", "Not Linked", "#7a8ba0"),
    ]

    for icon, name, status, color in llm_providers:
        st.markdown(f"""
        <div class="overview-item">
            <span style="font-size:14px;">{icon}</span>
            <div>
                <div class="overview-label" style="font-size:13px;">{name}</div>
                <div style="font-family:'Share Tech Mono',monospace; font-size:11px; color:{color};">{status}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ── Row 3: Timeline charts ──────────────────────────────────────────────────

col_cpu_chart, col_ram_chart = st.columns(2)


def _dark_line_chart(timestamps, values, title, unit, color="#00d4ff") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=values, mode="lines+markers",
        line=dict(color=color, width=2),
        marker=dict(size=3, color=color),
        fill="tozeroy",
        fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(family="Rajdhani", size=14, color="#e0e6ed")),
        height=250,
        margin=dict(t=40, b=30, l=50, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, color="#7a8ba0", type="date"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,212,255,0.05)", color="#7a8ba0",
                   title=dict(text=unit, font=dict(size=10))),
        font=dict(family="Share Tech Mono", size=10),
    )
    return fig


with col_cpu_chart:
    st.markdown("""<div class="friday-card">
        <div class="friday-card-title">CPU Timeline</div>
    """, unsafe_allow_html=True)
    ts, vals = _time_series("system", "cpu_percent")
    if ts:
        st.plotly_chart(_dark_line_chart(ts, vals, "", "%", "#00d4ff"), width="stretch")
    else:
        st.info("Sin datos de CPU. Iniciá los collectors con `python -m friday.main`.")
    st.markdown("</div>", unsafe_allow_html=True)

with col_ram_chart:
    st.markdown("""<div class="friday-card">
        <div class="friday-card-title">RAM Timeline</div>
    """, unsafe_allow_html=True)
    ts, vals = _time_series("system", "ram_percent")
    if ts:
        st.plotly_chart(_dark_line_chart(ts, vals, "", "%", "#00ffc8"), width="stretch")
    else:
        st.info("Sin datos de RAM. Iniciá los collectors con `python -m friday.main`.")
    st.markdown("</div>", unsafe_allow_html=True)


# ── Footer ───────────────────────────────────────────────────────────────────

st.markdown(f"""
<div style="text-align:center; padding:20px 0 10px; border-top:1px solid rgba(0,212,255,0.1); margin-top:20px;">
    <span style="font-family:'Orbitron',monospace; font-size:14px; letter-spacing:4px;
                 color:rgba(0,212,255,0.6);">FRIDAY</span>
    <span style="font-family:'Share Tech Mono',monospace; font-size:11px; color:#7a8ba0;
                 margin-left:12px;">v0.1.0 · Gemini-Powered · {now_local.strftime('%H:%M:%S')}</span>
</div>
""", unsafe_allow_html=True)

# ── Auto-refresco ────────────────────────────────────────────────────────────

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=10_000, key="friday_refresh")
except ImportError:
    pass
