import streamlit as st
import pandas as pd
import numpy as np
import os
import time
from datetime import datetime
from loguru import logger
from collections import deque

# Services
from services.utils import MSK
from services.auth import render_sidebar_auth, get_invest_token
from services.market import (
    get_tickers, get_selected_tickers, save_selected_tickers, 
    save_tickers, fetch_all_moex_shares
)

# UI Components
from ui.shared import inject_css, build_all_tables_snapshot_text
from ui.dashboard import render_dashboard
from ui.squeeze import render_squeeze
from ui.portfolio import render_portfolio
from ui.dividends import render_dividends
from ui.sandbox import render_sandbox
from ui.strategy import render_strategy
from ui.logs import render_logs

from st_copy_to_clipboard import st_copy_to_clipboard
from streamlit_autorefresh import st_autorefresh

# ═════════════════════════════════════════════════════════════════════
# CONFIGURATION & LOGGING
# ═════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Vostok Terminal",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

_LOGS_DIR = "logs"
os.makedirs(_LOGS_DIR, exist_ok=True)

if "GLOBAL_LOG_QUEUE" not in st.session_state:
    st.session_state["GLOBAL_LOG_QUEUE"] = deque(maxlen=200)

GLOBAL_LOG_QUEUE = st.session_state["GLOBAL_LOG_QUEUE"]

# Patch loguru to use Moscow Time (UTC+3)
def _patch_msk(record):
    record["time"] = record["time"].astimezone(MSK)

logger.remove()
logger.configure(patcher=_patch_msk)
logger.add(os.sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")
logger.add(
    lambda msg: GLOBAL_LOG_QUEUE.append(msg),
    format="{time:HH:mm:ss} | {level} | {message}",
    level="INFO"
)

def log(msg: str, level: str = "INFO"):
    if level.upper() == "ERROR": logger.error(msg)
    elif level.upper() == "WARNING": logger.warning(msg)
    else: logger.info(msg)

def get_log_text() -> str:
    return "".join(GLOBAL_LOG_QUEUE)

# ═════════════════════════════════════════════════════════════════════
# SESSION STATE INITIALIZATION
# ═════════════════════════════════════════════════════════════════════
state_defaults = {
    "market_data": {},
    "squeeze_data": {},
    "portfolio_data": {},
    "dividend_data": [],
    "sandbox_account_id": None,
    "sandbox_orders": [],
    "snapshot_dash_df": pd.DataFrame(),
    "snapshot_squeeze_df": pd.DataFrame(),
    "snapshot_positions_df": pd.DataFrame(),
    "snapshot_dividends_df": pd.DataFrame(),
    "focused_ticker": None,
    "trigger_scan": False,
}
for key, val in state_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ═════════════════════════════════════════════════════════════════════
# UI INJECTION & HEADER
# ═════════════════════════════════════════════════════════════════════
st.markdown(inject_css, unsafe_allow_html=True)

# Startup Sync: Force full scan on first load
if "first_run_triggered" not in st.session_state:
    st.session_state.trigger_scan = True
    st.session_state["first_run_triggered"] = True

# Top Bar Consolidation (Grouped Buttons & Status)
hcol1, hcol2, hcol3 = st.columns([12, 2, 2])
with hcol1:
    st.markdown('<div class="header-glow" style="margin-top: 5px; margin-bottom: 5px;"></div>', unsafe_allow_html=True)
    _status_placeholder = st.empty()
    
with hcol2:
    if st.button("🔄 Refresh", type="primary", width="stretch", help="Triggers a full Master Scan of all modules."):
        st.session_state.trigger_scan = True

with hcol3:
    # Render Copy button statically to prevent layout shifting
    st_copy_to_clipboard(
        text=build_all_tables_snapshot_text(),
        before_copy_label="📋 Copy Tables",
        after_copy_label="✅ Copied",
    )

# ═════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═════════════════════════════════════════════════════════════════════
st.sidebar.markdown(
    '<div style="text-align:center; padding:6px 0 2px 0;">'
    '<span style="font-size:2rem;">🚀</span><br>'
    '<span style="font-size:1.2rem; font-weight:700; color:#00e5ff; letter-spacing:0.08em;">VOSTOK WEB</span><br>'
    '<span style="font-size:0.7rem; color:#7a8a9e; letter-spacing:0.12em;">QUANTITATIVE TERMINAL</span>'
    "</div>",
    unsafe_allow_html=True,
)

render_sidebar_auth()
token = get_invest_token()

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚡ Auto-Scan")
auto_scan = st.sidebar.toggle("Enable Auto-Refresh", value=True, key="auto_scan")
scan_mode = st.sidebar.radio("Interval Mode", ["Preset", "Custom"], horizontal=True, key="scan_mode", label_visibility="collapsed")

if scan_mode == "Preset":
    scan_interval = st.sidebar.select_slider("Interval (sec)", options=[10, 15, 20, 30, 60, 120, 300], value=60, key="scan_interval", disabled=not auto_scan)
else:
    scan_interval = st.sidebar.number_input("Custom Interval (sec)", min_value=5, max_value=3600, value=45, step=5, key="scan_interval_custom", disabled=not auto_scan)

with st.sidebar.expander("⚙️ Tab Sync Inclusions"):
    auto_sync_dashboard = st.toggle("Dashboard", value=True, key="auto_sync_dashboard", disabled=not auto_scan)
    auto_sync_squeeze = st.toggle("Squeeze", value=True, key="auto_sync_squeeze", disabled=not auto_scan)
    auto_sync_portfolio = st.toggle("Portfolio", value=True, key="auto_sync_portfolio", disabled=not auto_scan)
    auto_sync_dividends = st.toggle("Dividends", value=False, key="auto_sync_dividends", disabled=not auto_scan)

sync_dashboard = (auto_scan and auto_sync_dashboard) or st.session_state.trigger_scan
sync_squeeze = (auto_scan and auto_sync_squeeze) or st.session_state.trigger_scan
sync_portfolio = (auto_scan and auto_sync_portfolio) or st.session_state.trigger_scan
sync_dividends = (auto_scan and auto_sync_dividends) or st.session_state.trigger_scan

st.sidebar.markdown("---")
all_tickers = get_tickers() # Ensure global available for all logic
with st.sidebar.expander("🛠 Manage Universe"):
    st.markdown("#### Search & Add Tickers")
    # Lazy-fetch full universe from API if not already present
    if "full_moex_universe" not in st.session_state:
        if token:
            with st.spinner("Fetching full MOEX universe..."):
                st.session_state["full_moex_universe"] = fetch_all_moex_shares(token)
        else:
            st.warning("Connect API token to search all instruments.")
            st.session_state["full_moex_universe"] = {}

    full_universe = st.session_state.get("full_moex_universe", {})
    if full_universe:
        existing = set(all_tickers.keys())
        available = sorted([t for t in full_universe.keys() if t not in existing])
        if available:
            to_add = st.selectbox("Select Ticker to Add", options=["Search Tickers..."] + available)
            if to_add != "Search Tickers...":
                if st.button("✅ Add Ticker", width="stretch"):
                    all_tickers[to_add] = full_universe[to_add]["uid"]
                    save_tickers(all_tickers)
                    st.success(f"Added {to_add}")
                    st.rerun()

    st.markdown("---")
    st.markdown("#### Active Ticker Filter")
    selected = st.multiselect(
        "Enabled Tickers",
        options=list(all_tickers.keys()),
        default=get_selected_tickers(),
        key="ticker_select"
    )
    
    if all_tickers:
        st.markdown("---")
        st.markdown("#### Remove Tickers")
        to_remove = st.selectbox("Select Ticker to Remove", options=["-- Select Ticker --"] + sorted(all_tickers.keys()))
        if to_remove != "-- Select Ticker --":
            if st.button("🗑️ Remove Ticker", width="stretch"):
                del all_tickers[to_remove]
                save_tickers(all_tickers)
                st.warning(f"Removed {to_remove}")
                st.rerun()

# Sync focus ticker
if selected:
    if st.session_state.focused_ticker not in selected:
        st.session_state.focused_ticker = selected[0]
else:
    st.session_state.focused_ticker = None

if selected != get_selected_tickers():
    save_selected_tickers(selected)

selected_tickers = {t: all_tickers[t] for t in selected if t in all_tickers}
tickers_tuple = tuple(sorted(selected_tickers.items()))

# Ticker manager removed from sidebar and moved to Config tab

# ═════════════════════════════════════════════════════════════════════
# MAIN TABS
# ═════════════════════════════════════════════════════════════════════
# Fixed ~1cm gap for layout stability
st.markdown("<div style='height: 38px;'></div>", unsafe_allow_html=True)

tab_dash, tab_squeeze, tab_port, tab_divs, tab_strat, tab_sandbox, tab_cfg, tab_logs = st.tabs([
    "📈 Dashboard", "💥 Squeeze", "💼 Portfolio", "📅 Dividends",
    "🧠 Strategy", "🎮 Sandbox", "🛠 Config", "📜 Logs",
])

with tab_dash: 
    render_dashboard(token, tickers_tuple, sync_dashboard, log, _status_placeholder)

with tab_squeeze:
    render_squeeze(token, tickers_tuple, sync_squeeze, log, _status_placeholder)

with tab_port:
    render_portfolio(token, sync_portfolio, log)

with tab_divs:
    render_dividends(token, tickers_tuple, sync_dividends, log)

with tab_strat:
    render_strategy(token, tickers_tuple, log)

with tab_sandbox:
    render_sandbox(token, log)

with tab_cfg:
    st.markdown("Manage your instruments in the sidebar under 'Manage Universe'.")

with tab_logs:
    render_logs(get_log_text, GLOBAL_LOG_QUEUE, _LOGS_DIR, log)

# Reset trigger_scan at the end of the script run
if st.session_state.trigger_scan:
    st.session_state.trigger_scan = False

# Auto-refresh and script end logic...

# ═════════════════════════════════════════════════════════════════════
# AUTO-REFRESH LOOP
# ═════════════════════════════════════════════════════════════════════
if auto_scan and token and selected_tickers:
    st_autorefresh(interval=int(scan_interval * 1000), key="vostok_auto_refresh")
    st.info(f"⚡ Auto-refresh active - next scan in {scan_interval}s")
