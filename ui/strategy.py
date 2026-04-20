import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from services.market import run_coro_sync, fetch_candles_async, get_tickers
from t_tech.invest import AsyncClient

def render_strategy(token, tickers_tuple, log):
    selected_tickers = dict(tickers_tuple)
    
    st.markdown(
        '<div style="background:linear-gradient(135deg,#111820,#162030); border:1px solid #1c2838;'
        'border-radius:12px; padding:16px; margin-bottom:12px;">'
        '<h3 style="color:#00e5ff; margin:0;">🧠 Strategy Backtest Analytics</h3>'
        '<p style="color:#7a8a9e; margin:4px 0 0 0; font-size:0.85rem;">Simulated equity curves and drawdown analysis.</p>'
        "</div>",
        unsafe_allow_html=True,
    )

    s1, s2 = st.columns([2, 1])
    with s1:
        st.markdown("##### Parameters")
        c1, c2 = st.columns(2)
        strategy = c1.selectbox("Select Strategy", ["Buy The Dip", "Volatility Squeeze"], key="strat_sel")
        bt_options = list(selected_tickers.keys()) if selected_tickers else ["SBER"]
        
        bt_idx = 0
        if st.session_state.focused_ticker in bt_options:
            bt_idx = bt_options.index(st.session_state.focused_ticker)
            
        bt_ticker = c2.selectbox("Target Asset", bt_options, index=bt_idx, key="bt_ticker")
        st.session_state.focused_ticker = bt_ticker
    with s2:
        st.markdown("<br>", unsafe_allow_html=True)
        run_bt = st.button("▶ Run Backtest", type="primary", key="run_bt", width="stretch")

    if run_bt and token:
        st.session_state["backtest_ran"] = True
        
        with st.spinner(f"⏳ Fetching 1.5-year history for {bt_ticker} & crunching stats..."):
            uid = selected_tickers.get(bt_ticker, "e6123145-9665-43e0-8413-cd61b8aa9b13")
            
            async def _fetch_hist():
                async with AsyncClient(token) as client:
                    return await fetch_candles_async(client, uid, 380) # ~1.5 years trading days

            candle_data = run_coro_sync(_fetch_hist)

            # Fix for dictionary parsing
            candles = candle_data.get("1D", []) if isinstance(candle_data, dict) else candle_data

            if not candles or len(candles) < 60:
                st.error("Not enough historical data to generate a valid backtest.")
            else:
                from services.indicators import prepare_candle_data, calculate_indicators
                df = prepare_candle_data(candles)
                df = calculate_indicators(df)
                
                # Strategy logic
                df["Btw_Dip_Signal"] = (df["RSI"] < 35) & (df["MACD_HISTOGRAM"] > df["MACD_HISTOGRAM"].shift(1)) & (df["close"] <= df["BB_LOWER"] * 1.01)
                
                df["BB_WIDTH"] = (df["BB_UPPER"] - df["BB_LOWER"]) / df["BB_MIDDLE"]
                df["BB_WIDTH_RANK"] = df["BB_WIDTH"].rolling(window=120, min_periods=30).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
                df["Squeeze_Signal"] = (df["BB_WIDTH_RANK"] < 0.20) & (df["MACD_HISTOGRAM"] > df["MACD_HISTOGRAM"].shift(1)) & (df["MACD_HISTOGRAM"].shift(1) < 0)
                
                signals = df["Btw_Dip_Signal"] if strategy == "Buy The Dip" else df["Squeeze_Signal"]
                
                # Forward 5-day return (Enter next open, exit 5 closes later)
                df["Fwd_5d_Ret"] = (df["close"].shift(-5) - df["open"].shift(-1)) / df["open"].shift(-1)
                
                equity_curve = [100_000.0] * len(df)
                eq = 100_000.0
                win_count = 0
                trade_count = 0
                
                i = 50 # Start after enough warmup
                while i < len(df) - 5:
                    if signals.iloc[i]:
                        ret = df["Fwd_5d_Ret"].iloc[i]
                        if not np.isnan(ret):
                            eq = eq * (1 + ret)
                            if ret > 0: win_count += 1
                            trade_count += 1
                            for j in range(5):
                                if i + j + 1 < len(df):
                                    equity_curve[i + j + 1] = eq
                            i += 5 # Skip holdings period
                        else:
                            i += 1
                    else:
                        if i + 1 < len(df):
                            equity_curve[i + 1] = eq
                        i += 1
                        
                # Fill remaining tail
                for j in range(i, len(df)):
                    equity_curve[j] = eq
                
                equity = np.array(equity_curve)
                peak = np.maximum.accumulate(equity)
                drawdown = ((equity - peak) / peak) * 100
                
                total_ret = ((equity[-1] / 100_000) - 1) * 100
                max_dd = np.min(drawdown)
                win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0.0

                equity = np.array(equity_curve)
                peak = np.maximum.accumulate(equity)
                drawdown = ((equity - peak) / peak) * 100
                
                total_ret = ((equity[-1] / 100_000) - 1) * 100
                max_dd = np.min(drawdown)
                win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0.0

                # Metric Cards
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("📊 Total Return", f"{total_ret:+.2f}%")
                s2.metric("📉 Max Drawdown", f"{max_dd:.2f}%")
                s3.metric("🎯 Win Rate", f"{win_rate:.1f}%")
                s4.metric("💰 Final Equity", f"₽ {equity[-1]:,.0f}")

                # Synced Charts (Equity + Drawdown)
                from plotly.subplots import make_subplots
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                    vertical_spacing=0.1, row_heights=[0.7, 0.3],
                                    subplot_titles=(f"Equity Curve - {bt_ticker}", "Drawdown (%)"))
                
                # Equity Path
                fig.add_trace(go.Scatter(x=df.index, y=equity, name="Equity", 
                                        line=dict(color="#00e5ff", width=2.5), 
                                        fill="tozeroy", fillcolor="rgba(0,229,255,0.05)"), row=1, col=1)
                
                # Drawdown Path
                fig.add_trace(go.Scatter(x=df.index, y=drawdown, name="Drawdown", 
                                        line=dict(color="#ff5252", width=1.5),
                                        fill="tozeroy", fillcolor="rgba(255,82,82,0.1)"), row=2, col=1)
                
                fig.update_layout(
                    template="plotly_dark", height=550,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=10, r=10, t=50, b=10), showlegend=False,
                    font=dict(family="Outfit, sans-serif", size=12),
                )
                fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)", zeroline=False)
                fig.update_xaxes(showgrid=False)
                
                st.plotly_chart(fig, width="stretch")

                # Trade History (Simulation Logic Refetch)
                st.markdown("---")
                st.subheader("📝 Simulation Trade Log")
                
                trade_log = []
                sq_eq = 100_000.0
                ti = 50
                while ti < len(df) - 5:
                    if signals.iloc[ti]:
                        ret = df["Fwd_5d_Ret"].iloc[ti]
                        if not np.isnan(ret):
                            entry_p = df["open"].shift(-1).iloc[ti]
                            exit_p = df["close"].shift(-5).iloc[ti]
                            pnl_pct = ret * 100
                            pnl_val = sq_eq * ret
                            sq_eq *= (1 + ret)
                            trade_log.append({
                                "Entry Date": df.index[ti+1].strftime("%Y-%m-%d"),
                                "Exit Date": df.index[min(ti+6, len(df)-1)].strftime("%Y-%m-%d"),
                                "Entry Price": f"{entry_p:,.2f}",
                                "Exit Price": f"{exit_p:,.2f}",
                                "P&L (%)": f"{pnl_pct:+.2f}%",
                                "Result": "✅ WIN" if ret > 0 else "❌ LOSS"
                            })
                            ti += 5
                        else: ti += 1
                    else: ti += 1
                
                if trade_log:
                    tdf = pd.DataFrame(trade_log)
                    st.dataframe(tdf, width="stretch", hide_index=True)
                else:
                    st.info("No trades executed during the simulation period.")
                
                log(f"Backtest {bt_ticker}: {strategy} - Trades={trade_count} Ret={total_ret:.2f}%")
    elif run_bt and not token:
        st.warning("⚠️ Connect API Token to run backtests.")
