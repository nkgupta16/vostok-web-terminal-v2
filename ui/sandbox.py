import streamlit as st
import pandas as pd
from datetime import datetime
from services.portfolio import (
    get_all_sandbox_accounts, sandbox_init, close_sandbox_account,
    fetch_portfolio, sandbox_deposit, sandbox_order
)
from services.market import get_selected_tickers
from services.utils import MSK
from ui.shared import _style_spos, df_to_tsv

def calculate_position_size(capital, risk_per_trade, stop_loss_pct, price, lot_size):
    """Shim for position size calculation."""
    risk_amount = capital * risk_per_trade
    stop_loss_amount = price * stop_loss_pct
    if stop_loss_amount == 0: return {"lots": 0, "shares": 0, "position_value": 0}
    shares = int(risk_amount / stop_loss_amount)
    lots = max(1, shares // lot_size)
    actual_shares = lots * lot_size
    return {
        "lots": lots,
        "shares": actual_shares,
        "position_value": actual_shares * price
    }

def render_sandbox(token, log):
    if not token:
        st.warning("⚠️ Connect your T-Bank API token for Sandbox mode.")
        return

    st.markdown(
        '<div style="background:linear-gradient(135deg,#111820,#162030); border:1px solid #1c2838;'
        'border-radius:12px; padding:16px; margin-bottom:12px;">'
        '<h3 style="color:#00e5ff; margin:0;">🎮 Virtual Sandbox</h3>'
        '<p style="color:#7a8a9e; margin:4px 0 0 0; font-size:0.85rem;">Paper trading with T-Bank Sandbox API. No real money at risk.</p>'
        "</div>",
        unsafe_allow_html=True,
    )

    # Sandbox Account Selection UI
    accounts = get_all_sandbox_accounts(token)
    
    sc1, sc2, sc3 = st.columns([2, 1, 1])
    with sc1:
        if accounts:
            current_sb_id = st.session_state.get("sandbox_account_id")
            selected_acc = st.selectbox(
                "Active Sandbox Accounts", 
                options=accounts,
                index=accounts.index(current_sb_id) if current_sb_id in accounts else 0
            )
            if selected_acc:
                st.session_state["sandbox_account_id"] = selected_acc
        else:
            st.info("No Sandbox accounts found.")
            st.session_state["sandbox_account_id"] = None
    
    with sc2:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("➕ Create New", type="primary", width="stretch"):
            try:
                with st.spinner("Creating account..."):
                    acc_id = sandbox_init(token)
                    if acc_id:
                        st.session_state["sandbox_account_id"] = acc_id
                        st.success(f"Created: `{acc_id}`")
                        log(f"Sandbox created: {acc_id}")
                        st.rerun()
                    else:
                        st.error("Failed to create Sandbox (Limit Reached).")
            except Exception as e:
                st.error(f"Error: {e}")
                log(f"Sandbox init error: {e}", "ERROR")

    with sc3:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        sb_id = st.session_state.get("sandbox_account_id")
        if sb_id:
            if st.button("🗑️ Delete Account", width="stretch"):
                close_sandbox_account(token, sb_id)
                st.session_state.pop("sandbox_account_id", None)
                st.rerun()

    if st.session_state.get("sandbox_account_id"):
        sb_id = st.session_state["sandbox_account_id"]
        st.markdown(f"**Status:** 🟢 Account `{sb_id}` is active")

        with st.spinner("📂 Loading sandbox portfolio..."):
            sf = fetch_portfolio(token, sandbox_account_id=sb_id)

        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("Total Value", f"₽ {sf.get('total_value', 0):,.0f}")
        pc2.metric("Total P&L", f"₽ {sf.get('total_pnl', 0):,.0f}", delta=f"{sf.get('total_pnl', 0):+,.0f}")
        pc3.metric("Day P&L", f"₽ {sf.get('day_pnl', 0):,.0f}", delta=f"{sf.get('day_pnl', 0):+,.0f}")
        pc4.metric("Cash (RUB)", f"₽ {sf.get('cash', 0):,.0f}")

        if st.button("💰 Deposit 100K RUB", key="sb_deposit"):
            try:
                sandbox_deposit(token, sb_id)
                st.success("Deposited ₽100,000")
                log(f"Sandbox deposit: 100K RUB -> {sb_id}")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
                log(f"Sandbox deposit error: {e}", "ERROR")
        
        st.markdown("#### 📊 Sandbox Positions")
        if sf.get("positions"):
            df_spos = pd.DataFrame(sf["positions"])
            df_spos.columns = ["Ticker", "Qty", "Avg Price", "Last Price", "Value", "P&L", "P&L %", "Day P&L", "Day P&L %"]

            styled_spf = df_spos.style.apply(_style_spos, axis=None).background_gradient(
                subset=["P&L %", "Day P&L %"], cmap="RdYlGn", vmin=-5, vmax=5
            ).format({
                "Avg Price": "₽ {:.2f}", "Last Price": "₽ {:.2f}", "Value": "₽ {:,.0f}",
                "P&L": "₽ {:+,.0f}", "P&L %": "{:+.2f}%",
                "Day P&L": "₽ {:+,.0f}", "Day P&L %": "{:+.2f}%", "Qty": "{:.0f}",
            })
            st.dataframe(styled_spf, width="stretch", hide_index=True)
        else:
            st.info("No open positions in Sandbox.")
    else:
        st.markdown("**Status:** 🔴 Inactive")

    # Paper-trade BUY signals
    st.markdown("#### 📋 Paper Trade BUY Signals")
    mkt_data = st.session_state.get("market_data", {})
    if not mkt_data:
        st.info("Run Dashboard scan first to see BUY signals here.")
    else:
        buy_signals = {t: d for t, d in mkt_data.items() if str(d.get("label", "")).startswith("BUY")}
        if not buy_signals:
            st.info("No active BUY signals to paper-trade.")
        else:
            selected_tickers = get_selected_tickers()
            for ticker, d in buy_signals.items():
                with st.expander(f"🟢 {ticker} - ₽{d['price']:.2f}  (Confidence: {d['confidence']:.0f}%)"):
                    pos = calculate_position_size(50_000, 0.01, 0.02, d["price"], d.get("lot_size", 1))
                    st.markdown(f"**Lots:** {pos['lots']} - **Shares:** {pos['shares']} - **Value:** ₽{pos['position_value']:,.0f}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        ord_type = st.selectbox("Order Type", ["MARKET", "LIMIT"], key=f"sb_type_{ticker}")
                    with col2:
                        default_p = float(d["price"])
                        lim_price = st.number_input("Limit Price", value=default_p, format="%.2f", disabled=(ord_type=="MARKET"), key=f"sb_price_{ticker}")
                    
                    sb_acc = st.session_state.get("sandbox_account_id")
                    if st.button(f"🚀 Paper Execute {ticker}", key=f"sb_buy_{ticker}", disabled=not sb_acc):
                        try:
                            # We need the UID from tickers map
                            from services.market import get_tickers
                            tickers_map = get_tickers()
                            uid = tickers_map.get(ticker)
                            if not uid:
                                st.error(f"UID for {ticker} not found.")
                                return

                            order_id = sandbox_order(token, sb_acc, uid, pos["lots"], ord_type, lim_price)
                            
                            st.success(f"{ord_type} Order placed! ID: `{order_id}`")
                            log(f"Sandbox {ord_type} BUY: {ticker} x {pos['lots']} lots @ {lim_price if ord_type == 'LIMIT' else 'MARKET'} - order {order_id}")
                            
                            if "sandbox_orders" not in st.session_state:
                                st.session_state["sandbox_orders"] = []
                            st.session_state["sandbox_orders"].append({
                                "ticker": ticker, "type": ord_type, "lots": pos["lots"], "price": lim_price if ord_type == 'LIMIT' else d["price"],
                                "order_id": order_id, "time": datetime.now(MSK).strftime("%H:%M:%S"),
                            })
                        except Exception as e:
                            st.error(f"Order failed: {e}")
                            log(f"Sandbox BUY error ({ticker}): {e}", "ERROR")

    if st.session_state.get("sandbox_orders"):
        st.markdown("#### 📜 Order History")
        df_sb = pd.DataFrame(st.session_state["sandbox_orders"])
        st.dataframe(df_sb, width="stretch", hide_index=True)
