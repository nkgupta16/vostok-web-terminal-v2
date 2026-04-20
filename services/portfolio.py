"""
Vostok Web Terminal – Portfolio, Dividends & Account Service
=============================================================
Connects to T-Bank Invest API for account info, positions, dividend calendar,
and sandbox operations.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from t_tech.invest import (
    Client,
    CandleInterval,
    InstrumentIdType,
    InstrumentStatus,
    MoneyValue,
)
from t_tech.invest.utils import now

from services.utils import (
    is_retryable_api_error as _is_retryable_api_error,
    retry_wait_seconds as _retry_wait_seconds,
    money_to_float,
    quantity_to_float,
    float_to_quotation,
    get_account_id_from_config,
)


def _get_instrument_identity(client: Client, instrument_uid: str) -> Tuple[str, str]:
    inst = client.instruments.get_instrument_by(
        id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_UID,
        id=instrument_uid,
    )
    if not inst or not inst.instrument:
        return "", ""
    return inst.instrument.figi, inst.instrument.ticker


@st.cache_data(ttl=300, show_spinner=False)
def _get_prev_day_close(_token: str, figi: str) -> Optional[float]:
    with Client(_token) as cache_client:
        candles = list(
            cache_client.get_all_candles(
                instrument_id=figi,
                from_=datetime.now(timezone.utc) - timedelta(days=7),
                to=datetime.now(timezone.utc),
                interval=CandleInterval.CANDLE_INTERVAL_DAY,
            )
        )
    if len(candles) < 2:
        return None
    return money_to_float(candles[-2].close)


def _get_operations_with_retry(client: Client, account_id: str, sandbox_account_id: str = None):
    max_retries = 4
    for attempt in range(max_retries):
        try:
            if sandbox_account_id:
                return client.sandbox.get_sandbox_operations(
                    account_id=account_id,
                    from_=datetime.now(timezone.utc) - timedelta(days=30),
                    to=datetime.now(timezone.utc),
                )
            return client.operations.get_operations(
                account_id=account_id,
                from_=datetime.now(timezone.utc) - timedelta(days=30),
                to=datetime.now(timezone.utc),
            )
        except Exception as exc:
            if _is_retryable_api_error(exc) and attempt < max_retries - 1:
                time.sleep(_retry_wait_seconds(exc, attempt, cap=15))
                continue
            raise


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@st.cache_data(ttl=55, show_spinner=False)
def fetch_portfolio(_token: str, sandbox_account_id: str = None) -> dict:
    """
    Fetch portfolio positions, cash, P&L, and recent operations.
    If sandbox_account_id is provided, fetches from the Sandbox instead.
    """
    with Client(_token) as client:
        # Resolve account
        if sandbox_account_id:
            account_id = sandbox_account_id
        else:
            account_id = _resolve_account(client)
            if not account_id:
                return _empty_portfolio("No accounts found")

        # Fetch portfolio
        if sandbox_account_id:
            port = client.sandbox.get_sandbox_portfolio(account_id=account_id)
        else:
            port = client.operations.get_portfolio(account_id=account_id)

        # Fetch last prices + prev-day closes for each position
        last_prices: Dict[str, float] = {}
        prev_prices: Dict[str, float] = {}
        ticker_names: Dict[str, str] = {}
        uid_to_figi: Dict[str, str] = {}
        all_figis: List[str] = []

        # Pass 1: Resolve all FIGIs
        for pos in port.positions:
            try:
                figi, ticker = _get_instrument_identity(client, pos.instrument_uid)
                if not figi:
                    continue
                ticker_names[pos.instrument_uid] = ticker
                uid_to_figi[pos.instrument_uid] = figi
                all_figis.append(figi)
            except Exception:
                continue

        # Pass 2: Bulk fetch last prices
        if all_figis:
            try:
                pr = client.market_data.get_last_prices(
                    figi=all_figis,
                    instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE,
                )
                
                # Map responses back to UIDs
                figi_to_price = { 
                    item.figi: money_to_float(item.price) 
                    for item in pr.last_prices 
                }
                
                for uid, figi in uid_to_figi.items():
                    if figi in figi_to_price:
                        last_prices[uid] = figi_to_price[figi]
            except Exception as e:
                pass

        # Pass 3: Fetch cached prev-day closes
        for uid, figi in uid_to_figi.items():
            try:
                prev_close = _get_prev_day_close(_token, figi)
                if prev_close is not None:
                    prev_prices[uid] = prev_close
            except Exception:
                pass

        # Compute positions
        positions_out: List[dict] = []
        total_value = 0.0
        total_pnl = 0.0
        total_day_pnl = 0.0
        cash_balance = 0.0

        for pos in port.positions:
            if pos.instrument_type == "currency":
                cash_balance += float(pos.quantity.units)
                continue

            qty = quantity_to_float(pos.quantity) if pos.quantity else 0.0

            avg = money_to_float(pos.average_position_price) if pos.average_position_price else 0.0
                
            last = last_prices.get(pos.instrument_uid, avg)
            prev = prev_prices.get(pos.instrument_uid, last)

            value = qty * last
            pnl = (last - avg) * qty
            pnl_pct = (pnl / (avg * qty)) * 100 if avg * qty > 0 else 0
            day_pnl = (last - prev) * qty
            day_pnl_pct = ((last - prev) / prev) * 100 if prev > 0 else 0

            total_value += value
            total_pnl += pnl
            total_day_pnl += day_pnl

            positions_out.append({
                "ticker": ticker_names.get(pos.instrument_uid, pos.instrument_uid[:8]),
                "qty": qty,
                "avg_price": avg,
                "last_price": last,
                "value": value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "day_pnl": day_pnl,
                "day_pnl_pct": day_pnl_pct,
            })

        # Recent operations (last 30 days)
        ops_out: List[dict] = []
        try:
            ops = _get_operations_with_retry(client, account_id, sandbox_account_id)
            for op in ops.operations[:20]:
                op_amt = money_to_float(getattr(op, "payment", None)) or money_to_float(getattr(op, "amount", None))
                op_qty = quantity_to_float(getattr(op, "quantity", None))
                op_price = money_to_float(getattr(op, "price", None))

                ops_out.append({
                    "date": op.date.strftime("%Y-%m-%d %H:%M") if op.date else "",
                    "ticker": ticker_names.get(op.instrument_uid, op.instrument_uid[:8]),
                    "type": op.operation_type.name.replace("_", " ").title(),
                    "qty": op_qty,
                    "price": op_price,
                    "amount": op_amt,
                })
        except Exception:
            pass

        return {
            "total_value": total_value,
            "total_pnl": total_pnl,
            "day_pnl": total_day_pnl,
            "cash": cash_balance,
            "positions": positions_out,
            "operations": ops_out,
            "account_id": account_id,
            "ticker_names": ticker_names,
        }


# ---------------------------------------------------------------------------
# Dividend Calendar
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_dividends(
    _token: str,
    _tickers_tuple: tuple,
    portfolio_positions: Optional[Dict[str, dict]] = None,
) -> List[dict]:
    """
    Fetch upcoming dividends (next 6 months) for all tickers.
    Cross-references with portfolio to compute expected payout.
    """
    tickers = dict(_tickers_tuple)
    portfolio = portfolio_positions or {}
    events: List[dict] = []
    current = datetime.now(tz=timezone.utc)
    horizon = current + timedelta(days=180)

    with Client(_token) as client:
        for i, (ticker, uid) in enumerate(tickers.items()):
            if i > 0:
                time.sleep(0.2)  # Rate-limit safety
            try:
                resp = client.instruments.get_dividends(
                    instrument_id=uid,
                    from_=current,
                    to=horizon,
                )
                for div in resp.dividends:
                    if not hasattr(div, "record_date") or not div.record_date:
                        continue
                    rd = div.record_date
                    if rd.tzinfo is None:
                        rd = rd.replace(tzinfo=timezone.utc)
                    days_left = (rd - current).days
                    if days_left < 0 or days_left > 180:
                        continue

                    dps = 0.0
                    if hasattr(div, "dividend_net") and div.dividend_net:
                        dps = money_to_float(div.dividend_net)

                    shares_owned = portfolio.get(ticker, {}).get("qty", 0)
                    payout = shares_owned * dps

                    events.append({
                        "ticker": ticker,
                        "date": rd,
                        "div_per_share": dps,
                        "shares_owned": shares_owned,
                        "expected_payout": payout,
                        "days_left": days_left,
                    })
            except Exception as exc:
                if _is_retryable_api_error(exc):
                    time.sleep(_retry_wait_seconds(exc, 0, base=3, cap=12))
                    continue
                continue

    events.sort(key=lambda e: e["date"])
    return events


# ---------------------------------------------------------------------------
# Sandbox Operations
# ---------------------------------------------------------------------------

from loguru import logger

def get_all_sandbox_accounts(_token: str) -> List[str]:
    """Return a list of all sandbox account IDs."""
    try:
        with Client(_token) as client:
            accounts = client.sandbox.get_sandbox_accounts()
            return [acc.id for acc in accounts.accounts]
    except Exception as e:
        logger.error(f"Sandbox list error: {e}")
        return []

def sandbox_init(_token: str) -> str:
    """Create a new sandbox account."""
    try:
        with Client(_token) as client:
            logger.info("Sandbox init: creating new VostokWeb sandbox account.")
            resp = client.sandbox.open_sandbox_account(name="VostokWeb")
            return resp.account_id
    except Exception as e:
        logger.error(f"Sandbox init error (likely 35001 limit): {e}")
        return ""

def close_sandbox_account(_token: str, account_id: str):
    """Close an active sandbox account."""
    try:
        with Client(_token) as client:
            client.sandbox.close_sandbox_account(account_id=account_id)
            logger.info(f"Sandbox closed: {account_id}")
    except Exception as e:
        logger.error(f"Sandbox close error: {e}")


def sandbox_deposit(_token: str, account_id: str, amount: int = 100_000):
    """Deposit virtual RUB into sandbox account."""
    with Client(_token) as client:
        client.sandbox.sandbox_pay_in(
            account_id=account_id,
            amount=MoneyValue(units=amount, nano=0, currency="rub"),
        )


def sandbox_order(
    _token: str, account_id: str, uid: str, lots: int, order_type_str: str = "MARKET", limit_price: float = 0.0
) -> str:
    """Place a sandbox BUY order (MARKET or LIMIT)."""
    from t_tech.invest import OrderDirection, OrderType

    with Client(_token) as client:
        # Use Decimal-safe conversion to avoid float artifacts (e.g. 99.99 - 99)
        price_quotation = float_to_quotation(limit_price)

        otype = OrderType.ORDER_TYPE_LIMIT if order_type_str == "LIMIT" else OrderType.ORDER_TYPE_MARKET

        resp = client.sandbox.post_sandbox_order(
            account_id=account_id,
            instrument_id=uid,
            quantity=lots,
            direction=OrderDirection.ORDER_DIRECTION_BUY,
            order_type=otype,
            price=price_quotation if otype == OrderType.ORDER_TYPE_LIMIT else None,
        )
        return resp.order_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_account(client: Client) -> Optional[str]:
    """Find the target account from config, falling back to first brokerage account."""
    try:
        resp = client.users.get_accounts()
        # Try configured account first (env var or Streamlit secret)
        target_id = get_account_id_from_config()
        if target_id:
            for acc in resp.accounts:
                if acc.id == target_id:
                    return acc.id
        # Fallback: first brokerage account
        for acc in resp.accounts:
            atype = getattr(acc, "account_type", None)
            if atype and "BROKER" in str(atype.name).upper():
                return acc.id
        # Fallback: first account
        if resp.accounts:
            return resp.accounts[0].id
    except Exception:
        pass
    return None


def _empty_portfolio(error: str = "") -> dict:
    return {
        "total_value": 0.0,
        "total_pnl": 0.0,
        "day_pnl": 0.0,
        "cash": 0.0,
        "positions": [],
        "operations": [],
        "account_id": "",
        "error": error,
    }
