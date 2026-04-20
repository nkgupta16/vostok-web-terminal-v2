import pandas as pd
from datetime import datetime
import io
import streamlit as st
from services.utils import MSK

# ---------------------------------------------------------------------------
# UI Styling Helpers
# ---------------------------------------------------------------------------
def _color_macd(val):
    try:
        v = float(val)
        color = '#00e676' if v > 0 else '#ff5252'
        return f'color: {color}; font-weight: bold'
    except Exception:
        return ''


def _color_signal(val):
    v = str(val).upper()
    if "BUY" in v:
        return 'color: #00ff88; font-weight: bold'
    elif "WATCH" in v:
        return 'color: #ffaa00; font-weight: bold'
    elif "NEUTRAL" in v:
        return 'color: #7a8a9e'
    elif "WEAK" in v or "SELL" in v:
        return 'color: #ff4b4b; font-weight: bold'
    return ''


def _color_bb(val):
    try:
        if float(val) <= 2.0:
            return 'color: #ffaa00; font-weight: bold'
    except Exception:
        pass
    return ''


def _color_vol(val):
    try:
        if float(val) >= 150.0:
            return 'color: #00e5ff; font-weight: bold'
    except Exception:
        pass
    return ''


def _style_pos(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for idx, row in df.iterrows():
        c = "color: #00e676" if row["P&L"] >= 0 else "color: #ff5252"
        styles.loc[idx, "P&L"] = c + "; font-weight: 600"
        styles.loc[idx, "P&L %"] = c
        dc = "color: #00e676" if row["Day P&L"] >= 0 else "color: #ff5252"
        styles.loc[idx, "Day P&L"] = dc
        styles.loc[idx, "Day P&L %"] = dc
    return styles


def _style_divs(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for idx, row in df.iterrows():
        days = row["Days to Cutoff"]
        if days <= 14:
            styles.loc[idx, "Days to Cutoff"] = "color: #ff5252; font-weight: 700"
        elif days <= 60:
            styles.loc[idx, "Days to Cutoff"] = "color: #ffab40"
        else:
            styles.loc[idx, "Days to Cutoff"] = "color: #00e676"
        
        payout_col = "Expected Payout (₽)"
        if payout_col in row and row[payout_col] and row[payout_col] > 0:
            styles.loc[idx, payout_col] = "color: #00e676; font-weight: 600"
    return styles


def _style_spos(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for idx, row in df.iterrows():
        c = "color: #00e676" if row["P&L"] >= 0 else "color: #ff5252"
        styles.loc[idx, "P&L"] = c + "; font-weight: 600"
        styles.loc[idx, "P&L %"] = c
        dc = "color: #00e676" if row["Day P&L"] >= 0 else "color: #ff5252"
        styles.loc[idx, "Day P&L"] = dc
        styles.loc[idx, "Day P&L %"] = dc
    return styles

# ---------------------------------------------------------------------------
# Data Export Helpers
# ---------------------------------------------------------------------------
def df_to_tsv(df: pd.DataFrame) -> str:
    """Convert DataFrame to tab-separated string for clipboard."""
    buf = io.StringIO()
    df.to_csv(buf, sep="\t", index=False)
    return buf.getvalue()


def build_all_tables_snapshot_text() -> str:
    """Build a single clipboard-friendly snapshot for dashboard, squeeze, positions, and dividends."""
    ts_utc_plus_3 = datetime.now(MSK)
    header = (
        "VOSTOK WEB TERMINAL - TABLE SNAPSHOT\n"
        f"Timestamp: {ts_utc_plus_3.strftime('%Y-%m-%d %H:%M:%S')} (UTC+3 / GMT+3)"
    )
    sections = [
        ("Dashboard", "snapshot_dash_df"),
        ("Squeeze", "snapshot_squeeze_df"),
        ("Current Positions", "snapshot_positions_df"),
        ("Dividends", "snapshot_dividends_df"),
    ]
    parts = [header]
    for title, key in sections:
        parts.append(f"\n=== {title} ===")
        df = st.session_state.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            parts.append(df_to_tsv(df))
        else:
            parts.append("(no data)")
    return "\n".join(parts)

# ---------------------------------------------------------------------------
# GLOBAL CSS
# ---------------------------------------------------------------------------
inject_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --accent: hsl(186, 100%, 50%);
    --accent-glow: hsla(186, 100%, 50%, 0.15);
    --bg-deep: hsl(210, 20%, 6%);
    --bg-card: hsla(210, 20%, 10%, 0.7);
    --bg-card-hover: hsla(210, 20%, 14%, 0.85);
    --border: hsla(210, 20%, 20%, 0.6);
    --text-main: hsl(210, 20%, 92%);
    --text-dim: hsl(210, 15%, 65%);
    --green: hsl(150, 100%, 45%);
    --red: hsl(0, 100%, 65%);
    --amber: hsl(40, 100%, 60%);
}

/* Global Aesthetics */
html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Outfit', sans-serif !important;
    background-color: var(--bg-deep) !important;
    color: var(--text-main);
}

.stMainBlockContainer { 
    padding-top: 4.5rem !important; /* Heavily reveal top bar borders */
    max-width: 95% !important;
}

/* Glassmorphism Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, hsla(210, 20%, 8%, 0.95) 0%, hsla(210, 20%, 5%, 0.98) 100%) !important;
    backdrop-filter: blur(12px);
    border-right: 1px solid var(--border);
}

/* Premium Header styling */
header[data-testid="stHeader"] {
    background: hsla(210, 20%, 6%, 0.8) !important;
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border);
}

/* Card-like Metrics */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    backdrop-filter: blur(4px);
    border: 1px solid var(--border) !important;
    border-radius: 16px !important;
    padding: 20px 24px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
[data-testid="stMetric"]:hover {
    transform: translateY(-4px) scale(1.02);
    border-color: var(--accent) !important;
    box-shadow: 0 12px 40px var(--accent-glow);
}
[data-testid="stMetricLabel"] { 
    color: var(--text-dim) !important; 
    font-weight: 500 !important; 
    letter-spacing: 0.1em; 
    text-transform: uppercase; 
    font-size: 0.7rem !important;
}
[data-testid="stMetricValue"] { 
    font-family: 'JetBrains Mono', monospace !important; 
    font-weight: 600 !important; 
    color: var(--accent) !important; 
    font-size: 1.8rem !important;
}

/* Tabs Optimization */
[data-testid="stTabs"] {
    margin-top: 1rem;
}
[data-testid="stTabs"] > div > div > button {
    font-family: 'Outfit', sans-serif !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.03em;
    padding: 10px 20px !important;
    border-radius: 12px 12px 0 0 !important;
    transition: all 0.2s ease !important;
}
[data-testid="stTabs"] > div > div > button[aria-selected="true"] {
    background: var(--bg-card) !important;
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
}

/* Professional Dataframes */
[data-testid="stDataFrame"] {
    background: var(--bg-card) !important;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--border);
}
[data-testid="stDataFrame"] th {
    background: hsla(210, 20%, 15%, 0.9) !important;
    color: var(--accent) !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    font-size: 0.75rem !important;
    padding: 12px !important;
    border-bottom: 2px solid var(--accent) !important;
}
[data-testid="stDataFrame"] td {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85rem !important;
    color: var(--text-main) !important;
    padding: 8px 12px !important;
}

/* Status Badges */
.scan-status {
    background: hsla(186, 100%, 50%, 0.08);
    border: 1px solid hsla(186, 100%, 50%, 0.25);
    border-radius: 8px;
    height: 38px;
    padding: 0 16px;
    color: var(--accent);
    font-weight: 600;
    font-size: 0.85rem;
    display: flex;
    align-items: center; /* Vertical Center */
    justify-content: flex-start;
    gap: 10px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    line-height: normal !important; /* Fix vertical sticking */
}
.scan-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 10px var(--accent);
    animation: pulse-dot 1.5s infinite;
}
@keyframes pulse-dot { 0%{opacity:0.4; transform:scale(0.8)} 50%{opacity:1; transform:scale(1.1)} 100%{opacity:0.4; transform:scale(0.8)} }

/* Buttons Enhancement */
.stButton > button {
    border-radius: 12px !important;
    font-weight: 600 !important;
    padding: 0.6rem 1.2rem !important;
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
.stButton > button:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    box-shadow: 0 0 15px var(--accent-glow) !important;
}

/* Global Button Centering Fix */
div.stButton > button {
    height: 38px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    line-height: normal !important;
    padding: 0 1rem !important;
}
div.stButton > button p {
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1 !important;
}
div.stButton > button div[data-testid="stMarkdownContainer"] p {
    margin: 0 !important;
}

/* Glow Elements */
.header-glow {
    background: linear-gradient(90deg, var(--accent), transparent);
    height: 2px;
    box-shadow: 0 0 12px var(--accent-glow);
    margin-bottom: 12px;
    border-radius: 2px;
    opacity: 0.5;
}

/* Strategy Visuals */
.breakout-pulse {
    background: hsla(150, 100%, 45%, 0.15);
    color: var(--green);
    border: 1px solid var(--green);
    animation: strategy-pulse 2s infinite;
    padding: 4px 12px;
    border-radius: 8px;
    font-weight: 700;
}
@keyframes strategy-pulse { 0%{box-shadow:0 0 0 0 rgba(0,230,118,0.4)} 70%{box-shadow:0 0 0 10px rgba(0,230,118,0)} 100%{box-shadow:0 0 0 0 rgba(0,230,118,0)} }
/* Strategy Trade Log */
[data-testid="stDataFrame"] {
    background: var(--bg-card) !important;
}

/* Portfolio Health Card Enhancements */
.health-badge {
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
}

/* Subheader Polish */
h1, h2, h3, h4, h5, h6 {
    color: var(--text-main) !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
}
</style>
"""
