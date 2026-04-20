import streamlit as st
import pandas as pd
from services.portfolio import fetch_portfolio
from ui.shared import _style_pos, df_to_tsv

def render_portfolio(token, sync_portfolio, log):
    if not token:
        st.warning("⚠️ Connect your T-Bank API token to view portfolio.")
        return
        
    if not sync_portfolio:
        st.info("⏸️ Portfolio auto-scan sync is OFF for this tab.")
        pf = st.session_state.get("portfolio_data", {})
    else:
        with st.spinner("📂 Loading portfolio..."):
            pf = fetch_portfolio(token)
            st.session_state["portfolio_data"] = pf
            log(f"Portfolio loaded - {len(pf.get('positions', []))} positions")

    if not pf:
        st.info("No portfolio data available.")
        return

    if pf.get("error"):
        st.error(pf["error"])
        return

    pc1, pc2, pc3, pc4 = st.columns(4)
    pc1.metric("📦 Portfolio Value", f"₽ {pf['total_value']:,.0f}")
    pc2.metric("📈 Total P&L", f"₽ {pf['total_pnl']:,.0f}", delta=f"{pf['total_pnl']:+,.0f}")
    pc3.metric("📅 Day P&L", f"₽ {pf['day_pnl']:,.0f}", delta=f"{pf['day_pnl']:+,.0f}")
    pc4.metric("💰 Available Cash", f"₽ {pf['cash']:,.0f}")

    st.markdown("---")
    main_col, health_col = st.columns([3, 1.2])

    with main_col:
        st.markdown("#### 📂 Active Positions")
        if pf.get("positions"):
            df_pos = pd.DataFrame(pf["positions"])
            df_pos.columns = ["Ticker", "Qty", "Avg Price", "Last Price", "Value", "P&L", "P&L %", "Day P&L", "Day P&L %"]
            st.session_state["snapshot_positions_df"] = df_pos.copy()

            styled_pf = df_pos.style.apply(_style_pos, axis=None).format({
                "Avg Price": "₽ {:.2f}", "Last Price": "₽ {:.2f}", "Value": "₽ {:,.0f}",
                "P&L": "₽ {:+,.0f}", "P&L %": "{:+.2f}%",
                "Day P&L": "₽ {:+,.0f}", "Day P&L %": "{:+.2f}%", "Qty": "{:.0f}",
            })

            st.dataframe(styled_pf, width="stretch", hide_index=True)
        else:
            st.info("No open positions.")

    with health_col:
        st.markdown("#### 🩺 Health Audit")
        mkt = st.session_state.get("market_data", {})
        if not mkt:
            st.info("Run Dashboard scan to audit health.")
        else:
            good_c, bad_c = 0, 0
            for pos_data in pf["positions"]:
                t = pos_data["ticker"]
                if t in mkt:
                    if mkt[t].get("confidence", 100) >= 50: good_c += 1
                    else: bad_c += 1
            
            # Health Summary Card
            total_audited = good_c + bad_c
            health_pct = (good_c / total_audited * 100) if total_audited > 0 else 0
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.1); '
                f'border-radius:12px; padding:12px; text-align:center;">'
                f'<span style="color:#7a8a9e; font-size:0.8rem;">Vostok Health Score</span><br>'
                f'<span style="color:{"#00e676" if health_pct >= 70 else "#ffab40"}; font-size:1.8rem; font-weight:700;">{health_pct:.0f}%</span>'
                f'</div>',
                unsafe_allow_html=True
            )
            
            for pos_data in pf["positions"]:
                t = pos_data["ticker"]
                if t in mkt:
                    md = mkt[t]
                    conf = md.get("confidence", 0)
                    color = "#00e676" if conf >= 70 else "#ffab40" if conf >= 45 else "#ff5252"
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">'
                        f'<span style="font-weight:600;">{t}</span>'
                        f'<span style="color:{color}; font-size:0.8rem; font-family:JetBrains Mono;">{conf:.0f}% Conf</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )

    st.markdown("---")
    with st.expander("📜 Recent Operations (Last 50)"):
        if pf.get("operations"):
            df_ops = pd.DataFrame(pf["operations"])
            df_ops.columns = ["Date", "Ticker", "Type", "Qty", "Price", "Amount"]
            st.dataframe(
                df_ops.style.format({"Price": "₽ {:.2f}", "Amount": "₽ {:+,.0f}", "Qty": "{:.0f}"}),
                width="stretch", hide_index=True,
            )
        else:
            st.info("No recent operations found.")
