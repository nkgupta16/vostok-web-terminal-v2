import streamlit as st
import pandas as pd
from datetime import datetime
from services.market import scan_squeeze
from services.utils import MSK
from ui.shared import df_to_tsv

def render_squeeze(token, tickers_tuple, sync_squeeze, log, _status_placeholder):
    selected_tickers = dict(tickers_tuple)
    
    if not token:
        st.warning("⚠️ Connect your T-Bank API token to enable Squeeze detection.")
        return
        
    if not sync_squeeze:
        st.info("⏸️ Squeeze auto-scan sync is OFF for this tab.")
        sq_data = st.session_state.get("squeeze_data", {})
    elif not selected_tickers:
        st.warning("⚠️ Select at least one ticker.")
        sq_data = {}
    else:
        _status_placeholder.markdown(
            '<div class="scan-status" title="Scanning for volatility squeezes..."><span class="scan-dot"></span>'
            f'Scanning {len(selected_tickers)} tickers… Squeeze Detection</div>',
            unsafe_allow_html=True,
        )
        with st.spinner(f"🔍 Scanning {len(selected_tickers)} tickers for squeezes…"):
            sq_data = scan_squeeze(token, tickers_tuple)
            st.session_state["squeeze_data"] = sq_data
            log(f"Squeeze scan complete - {len(sq_data)} tickers")
        _status_placeholder.markdown(
            '<div class="scan-status" style="border-color:rgba(0,230,118,0.3); color:#00e676;" title="Last successful volatility squeeze scan. Updates the Squeeze scoring table.">'
            f'✅ Squeeze scan complete - {len(sq_data)} tickers at {datetime.now(MSK).strftime("%H:%M:%S")}</div>',
            unsafe_allow_html=True,
        )

    if not sq_data:
        st.info("No squeeze data returned.")
    else:
        sorted_sq = sorted(
            sq_data.items(),
            key=lambda x: (
                0 if x[1]["metrics"]["is_breakout"] else 1,
                0 if x[1]["metrics"]["is_squeeze"] else 1,
                -x[1]["metrics"]["score"],
            ),
        )
        breakouts = [t for t, d in sorted_sq if d["metrics"]["is_breakout"]]
        if breakouts:
            for b in breakouts:
                st.toast(f"🚀 BREAKOUT: **{b}**", icon="🚀")
                log(f"BREAKOUT detected: {b}", "ALERT")

        rows_sq = []
        for ticker, d in sorted_sq:
            m = d["metrics"]
            if m["is_breakout"]:
                status = "🚀 BREAKOUT"
            elif m["is_squeeze"]:
                status = "🔥 SQUEEZE"
            else:
                status = "—"

            rows_sq.append({
                "Ticker": ticker,
                "Price": round(d["price"], 2),
                "BB Width %ile": round(m["score"], 1),
                "OBV Trend": f"{m['obv_trend']:+,.0f}",
                "ATR Ratio": round(m["atr_ratio"], 3),
                "Days in Squeeze": m["days_in_squeeze"],
                "Alert": status,
            })

        df_sq = pd.DataFrame(rows_sq)
        st.session_state["snapshot_squeeze_df"] = df_sq.copy()

        styled_sq = (
            df_sq.style
            .background_gradient(subset=["BB Width %ile"], cmap="YlOrRd", vmin=0, vmax=100)
            .background_gradient(subset=["ATR Ratio"], cmap="YlGnBu", vmin=0, vmax=3)
            .bar(subset=["Days in Squeeze"], color='#ff4081')
            .format({
                "Price": "{:,.2f}",
                "BB Width %ile": "{:.1f}%",
                "ATR Ratio": "{:.2f}",
            })
        )

        st.dataframe(styled_sq, width="stretch", hide_index=True, height=min(600, 40 + 35 * len(df_sq)))

        # Squeeze Visualizer
        import plotly.graph_objects as go
        st.markdown("---")
        st.subheader("🔥 Squeeze Visualizer (BB vs KC)")
        
        sq_options = df_sq["Ticker"].tolist()
        sq_idx = 0
        if st.session_state.focused_ticker in sq_options:
            sq_idx = sq_options.index(st.session_state.focused_ticker)
            
        sq_ticker = st.selectbox("Select Ticker to Visualize Squeeze", options=sq_options, index=sq_idx, key="sq_viz_ticker")
        st.session_state.focused_ticker = sq_ticker
        
        if sq_ticker:
            # We need the full DF for this ticker. 
            # Note: sq_data currently only returns price and metrics.
            # We'll need to modify scan_squeeze to return the DF too, or fetch it here.
            # To keep it efficient, we'll assume the user might have scanned it in Dashboard too.
            # For now, let's fetch it specifically if missing.
            from services.market import fetch_candles_async, prepare_candle_data, calculate_indicators, run_coro_sync, get_tickers
            from t_tech.invest import AsyncClient
            
            with st.spinner(f"Loading {sq_ticker} chart data..."):
                all_tickers_map = get_tickers()
                uid = all_tickers_map.get(sq_ticker)
                
                async def _get_df():
                    async with AsyncClient(token) as client:
                        from services.market import CANDLES_COUNT, SQUEEZE_CANDLES
                        from t_tech.invest import CandleInterval
                        from services.market import _fetch_interval_candles
                        candles = await _fetch_interval_candles(client, uid, CandleInterval.CANDLE_INTERVAL_DAY, 60, 60)
                        return calculate_indicators(prepare_candle_data(candles))
                
                sdf = run_coro_sync(_get_df)
                
                fig = go.Figure()
                # Price
                fig.add_trace(go.Candlestick(x=sdf.index, open=sdf["open"], high=sdf["high"], low=sdf["low"], close=sdf["close"], name="Price", opacity=0.4))
                
                # KC (The "Outer" Boundary for Squeeze)
                fig.add_trace(go.Scatter(x=sdf.index, y=sdf["KC_UPPER"], name="KC Upper", line=dict(color="#ffab40", width=1)))
                fig.add_trace(go.Scatter(x=sdf.index, y=sdf["KC_LOWER"], name="KC Lower", line=dict(color="#ffab40", width=1), fill="tonexty", fillcolor="rgba(255,171,64,0.05)"))
                
                # BB (The "Inner" Trigger)
                fig.add_trace(go.Scatter(x=sdf.index, y=sdf["BB_UPPER"], name="BB Upper", line=dict(color="#00e5ff", width=2)))
                fig.add_trace(go.Scatter(x=sdf.index, y=sdf["BB_LOWER"], name="BB Lower", line=dict(color="#00e5ff", width=2)))
                
                fig.update_layout(
                    title=f"{sq_ticker} - Squeeze Monitoring (BB must be inside KC)",
                    template="plotly_dark", height=400,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=40, b=10),
                )
                st.plotly_chart(fig, width="stretch")
                st.info("💡 **Squeeze Logic:** A high-probability explosive move is expected when the cyan Bollinger Bands (BB) "
                        "compress inside the orange Keltner Channels (KC).")
