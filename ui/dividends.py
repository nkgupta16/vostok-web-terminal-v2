import streamlit as st
import pandas as pd
from services.portfolio import fetch_dividends, fetch_portfolio
from services.market import get_tickers
from ui.shared import _style_divs, df_to_tsv

def render_dividends(token, tickers_tuple, sync_dividends, log):
    if not token:
        st.warning("⚠️ Connect your T-Bank API token to view dividends.")
        return
        
    if not sync_dividends:
        st.info("⏸️ Dividends auto-scan sync is OFF for this tab.")
        divs = st.session_state.get("dividend_data", [])
    else:
        # We need portfolio data to calculate expected payouts
        pf_for_divs = fetch_portfolio(token)
        portfolio_map = {p["ticker"]: p for p in pf_for_divs.get("positions", [])}

        with st.spinner("📅 Fetching dividend calendar..."):
            divs = fetch_dividends(token, tickers_tuple, portfolio_map)
            st.session_state["dividend_data"] = divs
            log(f"Dividend calendar - {len(divs)} upcoming events")

    if not divs:
        st.info("No upcoming dividends in the next 6 months.")
    else:
        rows_div = []
        for d in divs:
            price = None
            mkt = st.session_state.get("market_data", {})
            if mkt and d["ticker"] in mkt:
                price = mkt[d["ticker"]]["price"]
            yld = (d["div_per_share"] / price * 100) if price and price > 0 else None

            rows_div.append({
                "Ticker": d["ticker"],
                "Shares Owned": int(d["shares_owned"]),
                "Div/Share (₽)": round(d["div_per_share"], 2),
                "Expected Payout (₽)": round(d["expected_payout"], 2),
                "Yield est. %": round(yld, 2) if yld else None,
                "Date": d["date"].strftime("%Y-%m-%d") if hasattr(d["date"], "strftime") else str(d["date"]),
                "Days to Cutoff": d["days_left"],
            })

        df_div = pd.DataFrame(rows_div)
        st.session_state["snapshot_dividends_df"] = df_div.copy()

        st.dataframe(
            df_div.style.apply(_style_divs, axis=None)
            .background_gradient(subset=["Yield est. %"], cmap="Greens", vmin=0, vmax=15)
            .format(
                {
                    "Div/Share (₽)": "₽ {:.2f}", 
                    "Expected Payout (₽)": "₽ {:,.2f}", 
                    "Yield est. %": "{:.2f}%",
                },
                na_rep="-",
            ),
            width="stretch", hide_index=True,
        )
