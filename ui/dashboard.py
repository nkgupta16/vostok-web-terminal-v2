import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from t_tech.invest import AsyncClient
from services.market import scan_market, get_tickers, get_selected_tickers
from services.utils import MSK
from ui.shared import _color_macd, _color_signal, _color_bb, _color_vol, df_to_tsv

# Constants for Signal sorting
SIGNAL_SORT_ORDER = {
    "🚀 BUY (A+)": 0,
    "🟢 BUY": 1,
    "🟡 WATCH": 2,
    "⚪ NEUTRAL": 3,
    "🔴 WEAK": 4,
}

def render_dashboard(token, tickers_tuple, sync_dashboard, log, _status_placeholder):
    selected_tickers = dict(tickers_tuple)
    
    if not token:
        st.warning("⚠️ Connect your T-Bank API token in the sidebar to begin scanning.")
        data = {}
    elif sync_dashboard:
        if not selected_tickers:
            st.warning("⚠️ Select at least one ticker in the sidebar.")
            data = {}
        else:
            _status_placeholder.markdown(
                '<div class="scan-status" title="Scanning market data..."><span class="scan-dot"></span>'
                f'Scanning {len(selected_tickers)} tickers. Dashboard</div>',
                unsafe_allow_html=True,
            )
            with st.spinner(f"🔍 Scanning {len(selected_tickers)} tickers."):
                data = scan_market(token, tickers_tuple)
                st.session_state["market_data"] = data
            _status_placeholder.markdown(
                f'<div class="scan-status" style="border-color:rgba(0,230,118,0.3); color:#00e676;" title="Last successful market data scan. This updates Dashboard metrics.">'
                f'✅ Dashboard scan complete - {len(data)} tickers at {datetime.now(MSK).strftime("%H:%M:%S")}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.info("⏸️ Dashboard auto-scan sync is OFF for this tab.")
        data = st.session_state.get("market_data", {})

    if not data:
        if token and selected_tickers:
            st.error("No data returned. Check your token or network connection.")
            log("Dashboard scan returned empty", "ERROR")
    else:
        log(f"Dashboard scan complete - {len(data)} tickers")
        buy_count = sum(1 for d in data.values() if str(d.get("label", "")).startswith("BUY"))
        watch_count = sum(1 for d in data.values() if d["label"] == "WATCH")
        avg_rsi = np.mean([d["rsi"] for d in data.values()])
        
        # Safe strongest signal detection
        valid_conf = [d["confidence"] for d in data.values() if "confidence" in d]
        if valid_conf:
            strongest = max(data.items(), key=lambda x: x[1].get("confidence", 0))
            top_signal_text = f"{strongest[0]} ({strongest[1]['confidence']:.0f}%)"
        else:
            top_signal_text = "N/A"

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("🟢 BUY Signals", buy_count)
        mc2.metric("👁 WATCH Signals", watch_count)
        mc3.metric("📊 Avg RSI", f"{avg_rsi:.1f}")
        mc4.metric("🏆 Top Signal", top_signal_text)

        # Build DataFrame
        rows = []
        for ticker, d in data.items():
            rows.append({
                "Ticker": ticker,
                "Sector": d.get("sector", "Other"),
                "Price (RUB)": round(d["price"], 2),
                "Chandelier (₽)": round(d.get("chandelier_exit", 0), 2),
                "RSI": round(d["rsi"], 1),
                "vs BB (%)": round(d["price_to_bb"], 1),
                "Vol %": round(d["volume_ratio"], 0),
                "MACD Δ (%)": round(d["macd_change"], 1),
                "Confidence": round(d["confidence"], 1),
                "Signal": d["label"],
                "_sort": SIGNAL_SORT_ORDER.get(d["label"], 9),
            })

        df_display = pd.DataFrame(rows)
        df_display.sort_values(["_sort", "Confidence"], ascending=[True, False], inplace=True)
        df_display.drop(columns=["_sort"], inplace=True)
        df_display.reset_index(drop=True, inplace=True)
        st.session_state["snapshot_dash_df"] = df_display.copy()

        styled_df = (
            df_display.style
            .background_gradient(subset=["RSI"], cmap="RdYlGn", vmin=20, vmax=80)
            .map(_color_macd, subset=["MACD Δ (%)"])
            .map(_color_signal, subset=["Signal"])
            .map(_color_bb, subset=["vs BB (%)"])
            .map(_color_vol, subset=["Vol %"])
            .bar(subset=["Vol %"], color='#00e5ff', vmin=0, vmax=300)
            .format({
                "Price (RUB)": "{:,.2f}",
                "Chandelier (₽)": "{:,.2f}",
                "RSI": "{:.1f}",
                "vs BB (%)": "{:.1f}%",
                "Vol %": "{:.0f}%",
                "MACD Δ (%)": "{:.1f}%",
            })
        )

        st.dataframe(
            styled_df,
            column_config={
                "Confidence": st.column_config.ProgressColumn(
                    "Confidence %", help="Weighted quantitative score (0-100)",
                    format="%.0f%%", min_value=0, max_value=100,
                ),
            },
            width="stretch", hide_index=True,
            height=min(600, 40 + 35 * len(df_display)),
        )

        # Chart for selected ticker
        st.markdown("---")
        
        # Calculate index for focused ticker
        sorted_keys = sorted(data.keys())
        idx = 0
        if st.session_state.focused_ticker in sorted_keys:
            idx = sorted_keys.index(st.session_state.focused_ticker)
            
        chart_ticker = st.selectbox("📊 Select Ticker for Chart", options=sorted_keys, index=idx, key="chart_ticker")
        st.session_state.focused_ticker = chart_ticker # Update global focus

        if chart_ticker and chart_ticker in data:
            td = data[chart_ticker]
            chart_df = td["df"]

            # Main Price Chart (Candlestick + BB + EMA)
            fig = go.Figure()
            
            # 1. Candlestick
            fig.add_trace(go.Candlestick(
                x=chart_df.index,
                open=chart_df["open"], high=chart_df["high"],
                low=chart_df["low"], close=chart_df["close"],
                name="Price", increasing_line_color="#00e676", decreasing_line_color="#ff5252",
            ))
            
            # 2. Bollinger Bands
            fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["BB_UPPER"], name="BB Upper", line=dict(color="rgba(255,82,82,0.4)", width=1, dash="dot")))
            fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["BB_LOWER"], name="BB Lower", line=dict(color="rgba(0,229,255,0.4)", width=1, dash="dot"), fill="tonexty", fillcolor="rgba(0,229,255,0.02)"))
            
            # 3. EMA 20
            fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df.get("EMA_20"), name="EMA 20", line=dict(color="#ffab40", width=1.5)))

            fig.update_layout(
                title=f"{chart_ticker} - High Precision View", template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=450,
                xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                font=dict(family="Outfit, sans-serif", size=12, color="#e0e4ea"),
                xaxis=dict(showgrid=False, zeroline=False),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False),
            )
            st.plotly_chart(fig, width="stretch")

            # Volume & RSI Secondary Charts
            vcol1, vcol2 = st.columns([1, 1])
            with vcol1:
                fig_vol = go.Figure()
                # Color volume bars by close vs open
                vol_colors = ["#00e676" if row["close"] >= row["open"] else "#ff5252" for _, row in chart_df.iterrows()]
                fig_vol.add_trace(go.Bar(x=chart_df.index, y=chart_df["volume"], name="Volume", marker_color=vol_colors, opacity=0.6))
                fig_vol.update_layout(
                    title="Volume", template="plotly_dark", height=200,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
                    font=dict(family="Outfit, sans-serif", size=11),
                )
                st.plotly_chart(fig_vol, width="stretch")

            with vcol2:
                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(x=chart_df.index, y=chart_df["RSI"], name="RSI", line=dict(color="#00e5ff", width=2)))
                fig_rsi.add_hline(y=30, line_dash="dash", line_color="#ff5252", opacity=0.5)
                fig_rsi.add_hline(y=70, line_dash="dash", line_color="#ff5252", opacity=0.5)
                fig_rsi.update_layout(
                    title="RSI (14)", template="plotly_dark", height=200,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(range=[0, 100]), margin=dict(l=10, r=10, t=30, b=10),
                    font=dict(family="Outfit, sans-serif", size=11),
                )
                st.plotly_chart(fig_rsi, width="stretch")
