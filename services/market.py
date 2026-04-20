"""
Vostok Web Terminal – T-Bank API & Market Data Service
======================================================
Handles all T-Bank Invest API interactions: fetching candles, lot sizes,
share instrument lists, and computing per-ticker analytics.
"""

import json
import os
import asyncio
import concurrent.futures
from datetime import timedelta
from typing import Dict, List, Optional

from services.utils import (
    is_retryable_api_error as _is_retryable_api_error,
    retry_wait_seconds as _retry_wait_seconds,
    MAX_RETRIES,
)

import pandas as pd
import streamlit as st
from loguru import logger

from t_tech.invest import Client, AsyncClient, CandleInterval, InstrumentStatus
from t_tech.invest.utils import now

from services.indicators import (
    prepare_candle_data,
    calculate_indicators,
    check_buy_signal,
    calculate_confidence_score,
    calculate_squeeze_score,
    get_signal_label,
    BB_BUFFER,
    ATR_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Full MOEX Universe (from MOEX_Dip_Scanner gui_config.json)
# ---------------------------------------------------------------------------
DEFAULT_TICKERS: Dict[str, str] = {
    "SBER": "e6123145-9665-43e0-8413-cd61b8aa9b13",
    "GAZP": "962e2a95-02a9-4171-abd7-aa198dbe643a",
    "LKOH": "02cfdf61-6298-4c0f-a9ca-9cabc82afaf3",
    "GMKN": "509edd0c-129c-4ee2-934d-7f6246126da1",
    "NVTK": "0da66728-6c30-44c4-9264-df8fac2467ee",
    "ROSN": "fd417230-19cf-4e7b-9623-f7c9ca18ec6b",
    "VTBR": "8e2b0325-0292-4654-8a18-4f63ed3b0e09",
    "SNGSP": "a797f14a-8513-4b84-b15e-a3b98dc4cc00",
    "AFLT": "1c69e020-f3b1-455c-affa-45f8b8049234",
    "SFIN": "55371b1f-8f7c-4c12-9d93-386fae5ec12a",
    "HNFG": "2fa1d15e-236c-4e4e-8155-f740badfece6",
    "BELU": "974077c4-d893-4058-9314-8f1b64a444b8",
    "WUSH": "b993e814-9986-4434-ae88-b086066714a0",
    "BSPB": "1e19953d-01c6-4ecd-a5f4-53ae3ed44029",
    "VSEH": "538a1b13-df23-4449-8302-e8adbc25daf4",
    "BAZA": "6eeb0c40-1a7f-4b57-aeee-a3dbb3846b80",
    "POSI": "de08affe-4fbd-454e-9fd1-46a81b23f870",
    "FESH": "11bc2246-6fde-4478-93f1-4ab90ceb4a51",
    "EUTR": "02b2ea14-3c4b-47e8-9548-45a8dbcc8f8a",
    "X5": "0964acd0-e2cb-4810-a177-ef4ad8856ff0",
    "MVID": "cf1c6158-a303-43ac-89eb-9b1db8f96043",
    "OZON": "75e003c2-ca14-4980-8d7b-e82ec6b6ffe1",
    "ETLN": "b9dff600-4ca6-4fa9-ba91-df2126548ccc",
    "MBNK": "459a1a0a-0253-465a-bd4e-afaaf5e670b0",
    "MAGN": "7132b1c9-ee26-4464-b5b5-1046264b61d9",
    "MOEX": "5e1c2634-afc4-4e50-ad6d-f78fc14a539a",
    "MSNG": "98fc1318-6990-4147-b0d1-b10999326461",
    "NLMK": "161eb0d0-aaac-4451-b374-f5d0eeb1b508",
    "GLRX": "51be1fe4-9fe1-4626-9400-6cd1fb6286c5",
    "PLZL": "10620843-28ce-44e8-80c2-f26ceb1bd3e1",
    "PMSB": "4d8209f9-3b75-437d-ad5f-2906d56f27e9",
    "PMSBP": "80a39145-b2f7-46f5-9ef0-1478baafb0a6",
    "RUAL": "f866872b-8f68-4b6e-930f-749fe9aa79c0",
    "RENI": "a57d3a52-63d5-417b-b66d-c6114587f0ea",
    "MRKU": "1b64e38a-49ad-4f4d-a4d3-b34184899352",
    "RAGR": "9b9a584e-448f-40da-9ba8-353b44ad697a",
    "RNFT": "c7485564-ed92-45fd-a724-1214aa202904",
    "SBERP": "c190ff1f-1447-4227-b543-316332699ca5",
    "SNGS": "1ffe1bff-d7b7-4b04-b482-34dc9cc0a4ba",
    "TGKA": "d74daf58-22c3-4e44-8ada-471e404fb795",
    "TATN": "88468f6c-c67a-4fb4-a006-53eed803883c",
    "TATNP": "efdb54d3-2f92-44da-b7a3-8849e96039f6",
    "PHOR": "9978b56f-782a-4a80-a4b1-a48cbecfd194",
    "UGLD": "48bd9002-43be-4528-abf4-dc8135ad4550",
    "YDEX": "7de75794-a27f-4d81-a39b-492345813822",
    "LEAS": "ab29b599-4cb4-4b57-9c17-02b140708bf7",
    "LENT": "5f1e6b0a-4413-489c-b336-40b43730eaf5",
    "IRAO": "2dfbc1fd-b92a-436e-b011-928c79e805f2",
    "TRNFP": "653d47e9-dbd4-407a-a1c3-47f897df4694",
    "FLOT": "21423d2d-9009-4d37-9325-883b368d13ae",
    "AFKS": "53b67587-96eb-4b41-8e0c-d2e3c0bdd234",
    "HEAD": "3fe80143-1313-42eb-9884-5d68b39e265e",
    "SGZH": "7bedd86b-478d-4742-a28c-29d27f8dbc7d",
    "SMLT": "4d813ab1-8bc9-4670-89ea-12bfbab6017d",
    "ASTR": "aae786d8-e8f4-4428-91bb-cffa39ad01e4",
    "TGKB": "ba9b6eb4-614c-4be8-bdba-dd86cdfece64",
    "TGKBP": "45609688-b63e-42dd-88a0-9d30c423c5e5",
    "NSVZ": "88c3b1dd-cf86-48b6-b479-464ce1149472",
    "RBCM": "45fb6af4-9076-4268-b038-ab7f37d15ab2",
    "BANE": "0a55e045-e9a6-42d2-ac55-29674634af2f",
    "BANEP": "a5776620-1e2f-47ea-bbd6-06d8e4a236d8",
    "GTRK": "9e69afb6-4561-4fc2-b63b-b181e3f9ecdc",
    "FEES": "88e130e8-5b68-4b05-b9ae-baf32f5a3f21",
    "TTLK": "76721c1c-52a9-4b45-987e-d075f651f1b1",
    "DATA": "0b9afb23-280f-4fda-a7ad-816994959c6b",
    "FIXR": "8be64b53-a46b-451c-8152-1c871f122d5b",
    "MRKZ": "05dbfebd-6bc4-4645-8f21-dcf05476999d",
    "PIKK": "03d5e771-fc10-438e-8892-85a40733612d",
    "DOMRF": "aac2b935-3d94-4030-83a1-f7acdd9b05a5",
    "CHMF": "fa6aae10-b8d5-48c8-bbfd-d320d925d096",
    "VKCO": "b71bd174-c72c-41b0-a66f-5f9073e0d1f5",
    "MTLR": "eb4ba863-e85f-4f80-8c29-f2627938ee58",
    "MTLRP": "c1a3c440-f51c-4a75-a400-42a2a74f5f2b",
    "GCHE": "231e5e27-9956-47e7-ad50-6e802e4a92ed",
    "AQUA": "b83ab195-dcd2-4d44-b9bf-27fa294f19a0",
    "SELG": "0d28c01b-f841-4e89-9c92-0ee23d12883a",
}

TICKER_SECTORS: Dict[str, str] = {
    "SBER": "Financials", "SBERP": "Financials", "VTBR": "Financials", "TCSG": "Financials",
    "BSPB": "Financials", "MBNK": "Financials", "SFIN": "Financials", "MOEX": "Financials",
    "RENI": "Financials", "CBOM": "Financials", "SVCB": "Financials", "LEAS": "Financials",
    "GAZP": "Energy", "LKOH": "Energy", "ROSN": "Energy", "NVTK": "Energy",
    "SNGS": "Energy", "SNGSP": "Energy", "RNFT": "Energy", "TATN": "Energy", "TATNP": "Energy",
    "BANE": "Energy", "BANEP": "Energy", "TRNFP": "Energy",
    "GMKN": "Materials", "NLMK": "Materials", "MAGN": "Materials", "CHMF": "Materials",
    "RUAL": "Materials", "PLZL": "Materials", "UGLD": "Materials", "SELG": "Materials",
    "PHOR": "Materials", "ALRS": "Materials", "ENPG": "Materials", "MTLR": "Materials",
    "MTLRP": "Materials", "RASP": "Materials",
    "MTSS": "IT & Telecom", "RTKM": "IT & Telecom", "RTKMP": "IT & Telecom",
    "YDEX": "IT & Telecom", "OZON": "IT & Telecom", "VKCO": "IT & Telecom", "POSI": "IT & Telecom",
    "ASTR": "IT & Telecom", "HEAD": "IT & Telecom", "CIAN": "IT & Telecom",
    "PIKK": "Real Estate", "SMLT": "Real Estate", "ETLN": "Real Estate", "LSRG": "Real Estate",
    "MGNT": "Consumer", "X5": "Consumer", "FIVE": "Consumer", "MVID": "Consumer",
    "BELU": "Consumer", "MDMG": "Consumer", "HNFG": "Consumer", "LENT": "Consumer",
    "AQUA": "Consumer", "GCHE": "Consumer",
    "AFLT": "Transport", "FESH": "Transport", "FLOT": "Transport", "GLTR": "Transport",
    "IRAO": "Utilities", "FEES": "Utilities", "TGKA": "Utilities", "TGKB": "Utilities",
    "MSNG": "Utilities", "UPRO": "Utilities"
}

def get_sector(ticker: str) -> str:
    return TICKER_SECTORS.get(ticker, "Other")

CANDLES_COUNT = 50  # Daily candles to fetch for dashboard
SQUEEZE_CANDLES = 150  # More data needed for reliable squeeze percentiles
MAX_CONCURRENT_CANDLE_REQUESTS = 2
# ---------------------------------------------------------------------------
# Ticker Persistence (Hybrid: Session State + Disk)
# ---------------------------------------------------------------------------
_TICKER_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ticker_config.json")
_SELECTED_TICKERS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "selected_tickers_config.json"
)

def save_tickers(tickers: Dict[str, str]):
    """Persist the ticker map to session state and disk."""
    st.session_state["tickers"] = tickers
    try:
        with open(_TICKER_CONFIG_PATH, "w") as f:
            json.dump(tickers, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save tickers to disk: {e}")


def load_tickers() -> Dict[str, str]:
    """Load tickers from disk, falling back to session state then defaults."""
    if os.path.exists(_TICKER_CONFIG_PATH):
        try:
            with open(_TICKER_CONFIG_PATH) as f:
                data = json.load(f)
            if data:
                return data
        except Exception as e:
            logger.warning(f"Failed to load tickers from disk: {e}")
            
    if "tickers" in st.session_state:
        return st.session_state["tickers"]
    return dict(DEFAULT_TICKERS)


def get_tickers() -> Dict[str, str]:
    """Return the ticker -> UID map. Auto-generates ticker_config.json if missing."""
    if "tickers" not in st.session_state:
        if not os.path.exists(_TICKER_CONFIG_PATH):
            # First run or file lost: initialize with defaults and save to disk
            logger.info("Initializing ticker_config.json from defaults.")
            tickers = dict(DEFAULT_TICKERS)
            save_tickers(tickers) # This writes to disk and sets session_state
        else:
            st.session_state["tickers"] = load_tickers()
    return st.session_state["tickers"]


def get_selected_tickers() -> list:
    """Return the list of currently selected (enabled) ticker symbols."""
    all_tickers = get_tickers()
    if "selected_tickers" not in st.session_state:
        st.session_state["selected_tickers"] = load_selected_tickers(list(all_tickers.keys()))
    return st.session_state["selected_tickers"]


def save_selected_tickers(selected_tickers: List[str]):
    """Persist selected tickers to session state and disk."""
    unique_selected = list(dict.fromkeys(selected_tickers))
    st.session_state["selected_tickers"] = unique_selected
    try:
        with open(_SELECTED_TICKERS_CONFIG_PATH, "w") as f:
            json.dump(unique_selected, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save selected tickers to disk: {e}")


def load_selected_tickers(valid_tickers: List[str]) -> List[str]:
    """Load selected tickers from disk, falling back to session state."""
    valid_set = set(valid_tickers)
    
    if os.path.exists(_SELECTED_TICKERS_CONFIG_PATH):
        try:
            with open(_SELECTED_TICKERS_CONFIG_PATH) as f:
                raw = json.load(f)
            if isinstance(raw, list):
                filtered = [ticker for ticker in raw if ticker in valid_set]
                if filtered:
                    return filtered
        except Exception as e:
            logger.warning(f"Failed to load selected tickers from disk: {e}")

    if "selected_tickers" in st.session_state:
        raw = st.session_state["selected_tickers"]
        if isinstance(raw, list):
            filtered = [ticker for ticker in raw if ticker in valid_set]
            if filtered:
                return filtered
                
    return list(valid_tickers)


def fetch_all_moex_shares(token: str) -> Dict[str, dict]:
    """Fetch all MOEX shares from T-Bank API for the ticker manager."""
    results: Dict[str, dict] = {}
    try:
        with Client(token) as client:
            resp = client.instruments.shares(
                instrument_status=InstrumentStatus.INSTRUMENT_STATUS_ALL
            )
            for share in resp.instruments:
                exchange = (getattr(share, "exchange", "") or "").lower()
                if "moex" not in exchange:
                    continue
                if not bool(getattr(share, "api_trade_available_flag", False)):
                    continue
                if not getattr(share, "uid", None) or not getattr(share, "ticker", None):
                    continue
                if bool(getattr(share, "for_qual_investor_flag", False)):
                    continue
                if bool(getattr(share, "otc_flag", False)):
                    continue

                ticker = str(share.ticker).strip().upper()
                if not ticker:
                    continue

                existing = results.get(ticker)
                if existing and existing.get("api_trade_available", False):
                    continue

                api_trade_available = bool(getattr(share, "api_trade_available_flag", False))
                if existing and not existing.get("api_trade_available", False) and not api_trade_available:
                    continue

                class_code = (getattr(share, "class_code", "") or "").upper()
                exchange_label = (getattr(share, "exchange", "") or "").lower()

                rank = 0
                if "e_wknd" in exchange_label or "evng" in exchange_label:
                    rank -= 1
                if class_code in {"TQBR", "TQTF", "TQTD"}:
                    rank += 2
                if api_trade_available:
                    rank += 3
                if existing and rank <= existing.get("_rank", -999):
                    continue

                lot = int(getattr(share, "lot", 1) or 1)
                lot = max(lot, 1)
                name = (getattr(share, "name", "") or "").strip()
                figi = (getattr(share, "figi", "") or "").strip()

                results[ticker] = {
                    "uid": share.uid,
                    "name": name or ticker,
                    "lot": lot,
                    "figi": figi,
                    "class_code": class_code,
                    "exchange": exchange_label,
                    "api_trade_available": api_trade_available,
                    "_rank": rank,
                }
    except Exception as exc:
        logger.warning(f"Failed to fetch MOEX share universe: {exc}")
        return {}

    for ticker in list(results.keys()):
        results[ticker].pop("_rank", None)
    return results


# ---------------------------------------------------------------------------
# Data Fetching
# ---------------------------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_lot_sizes(_token: str, tickers_tuple: tuple) -> Dict[str, int]:
    """Fetch MOEX lot sizes for given tickers (cached 24h)."""
    lot_sizes: Dict[str, int] = {}
    tickers = dict(tickers_tuple)
    try:
        with Client(_token) as client:
            resp = client.instruments.shares(
                instrument_status=InstrumentStatus.INSTRUMENT_STATUS_BASE
            )
            for share in resp.instruments:
                if share.ticker in tickers:
                    lot_sizes[share.ticker] = getattr(share, "lot", 1) or 1
    except Exception:
        for t in tickers:
            lot_sizes[t] = 1
    return lot_sizes


def run_coro_sync(coro_func, *args):
    """Run an async coroutine synchronously in a dedicated thread to avoid Streamlit event-loop clashes."""
    def _run():
        return asyncio.run(coro_func(*args))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        return future.result()


# Retry logic is now in services.utils (shared with portfolio.py)

async def fetch_candles_async(client: AsyncClient, uid: str, days: int = CANDLES_COUNT) -> dict:
    """Fetch 1H, 4H, and 1D candles for an instrument UID asynchronously."""
    async def _fetch_interval(interval_enum, days_back, max_candles):
        try:
            from_time = now() - timedelta(days=days_back)
            to_time = now()
            candles = []
            async for c in client.get_all_candles(
                instrument_id=uid,
                from_=from_time,
                to=to_time,
                interval=interval_enum,
            ):
                candles.append(c)
            # Retain only the most recent requested buffer for performance
            if len(candles) > max_candles:
                candles = candles[-max_candles:]
            return candles
        except Exception as e:
            return []

    # Map intervals to fetch params. 1H needs ~5 days, 4H needs ~15, 1D needs `days`
    results = await asyncio.gather(
        _fetch_interval(CandleInterval.CANDLE_INTERVAL_DAY, days + 10, days),
        _fetch_interval(CandleInterval.CANDLE_INTERVAL_4_HOUR, 30, 60),
        _fetch_interval(CandleInterval.CANDLE_INTERVAL_HOUR, 10, 60)
    )
    
    return {
        "1D": results[0],
        "4H": results[1],
        "1H": results[2]
    }


async def _fetch_interval_candles(
    client: AsyncClient,
    uid: str,
    interval: CandleInterval,
    days_back: int,
    max_candles: int,
) -> list:
    from_time = now() - timedelta(days=days_back)
    to_time = now()
    candles = []
    async for c in client.get_all_candles(
        instrument_id=uid,
        from_=from_time,
        to=to_time,
        interval=interval,
    ):
        candles.append(c)
    if len(candles) > max_candles:
        candles = candles[-max_candles:]
    return candles

# ---------------------------------------------------------------------------
# Full Market Scan
# ---------------------------------------------------------------------------

async def _scan_market_batch(token: str, tickers: dict, lot_sizes: dict) -> dict:
    results = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CANDLE_REQUESTS)

    async def process_ticker(client: AsyncClient, ticker: str, uid: str):
        for attempt in range(MAX_RETRIES):
            try:
                async with semaphore:
                    candles_1d = await _fetch_interval_candles(
                        client,
                        uid,
                        CandleInterval.CANDLE_INTERVAL_DAY,
                        CANDLES_COUNT + 10,
                        CANDLES_COUNT,
                    )

                if not candles_1d or len(candles_1d) < 2:
                    return

                df = calculate_indicators(prepare_candle_data(candles_1d))

                latest = df.iloc[-1]
                previous = df.iloc[-2]

                price = float(latest["close"])
                rsi = float(latest["RSI"])
                bb_lower = float(latest["BB_LOWER"])
                bb_upper = float(latest["BB_UPPER"])
                macd_hist = float(latest["MACD_HISTOGRAM"])
                prev_hist = float(previous["MACD_HISTOGRAM"])
                vol = float(latest["volume"])

                # Volume ratio vs 10d average
                if len(df) >= 10:
                    avg_vol = float(df["volume"].iloc[-11:-1].mean())
                    vol_ratio = (vol / avg_vol) * 100 if avg_vol > 0 else 100.0
                else:
                    vol_ratio = 100.0

                # Derived metrics
                price_to_bb = ((price - bb_lower) / bb_lower) * 100 if bb_lower else 0
                macd_change = (
                    ((macd_hist - prev_hist) / abs(prev_hist)) * 100
                    if prev_hist != 0
                    else 0.0
                )

                is_buy, _, _ = check_buy_signal(df, bb_buffer=BB_BUFFER)
                is_aplus = False
                if is_buy:
                    async with semaphore:
                        candles_4h, candles_1h = await asyncio.gather(
                            _fetch_interval_candles(
                                client, uid, CandleInterval.CANDLE_INTERVAL_4_HOUR, 30, 60
                            ),
                            _fetch_interval_candles(
                                client, uid, CandleInterval.CANDLE_INTERVAL_HOUR, 10, 60
                            ),
                        )
                    df_4h = (
                        calculate_indicators(prepare_candle_data(candles_4h))
                        if len(candles_4h) > 1
                        else None
                    )
                    df_1h = (
                        calculate_indicators(prepare_candle_data(candles_1h))
                        if len(candles_1h) > 1
                        else None
                    )
                    is_buy, _, is_aplus = check_buy_signal(
                        df, df_4h=df_4h, df_1h=df_1h, bb_buffer=BB_BUFFER
                    )

                confidence = calculate_confidence_score(
                    rsi=rsi,
                    price=price,
                    bb_lower=bb_lower,
                    bb_upper=bb_upper,
                    volume_ratio=vol_ratio,
                    macd_hist=macd_hist,
                    macd_change=macd_change,
                )

                label = get_signal_label(confidence, is_buy, is_aplus)

                results[ticker] = {
                    "price": price,
                    "rsi": rsi,
                    "bb_lower": bb_lower,
                    "bb_upper": bb_upper,
                    "bb_middle": float(latest["BB_MIDDLE"]),
                    "macd_hist": macd_hist,
                    "macd_change": macd_change,
                    "volume_ratio": vol_ratio,
                    "price_to_bb": price_to_bb,
                    "signal": is_buy,
                    "confidence": confidence,
                    "label": label,
                    "lot_size": lot_sizes.get(ticker, 1),
                    "sector": get_sector(ticker),
                    "chandelier_exit": float(latest.get("CHANDELIER_EXIT", 0)),
                    "df": df,
                }
                return  # Success
            except Exception as e:
                if _is_retryable_api_error(e):
                    if attempt < MAX_RETRIES - 1:
                        wait = _retry_wait_seconds(e, attempt)
                        logger.warning(
                            f"Retryable market error on {ticker}, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Market scan error for {ticker}: exhausted {MAX_RETRIES} retries")
                else:
                    logger.error(f"Market scan error for {ticker}: {e}")
                    return

    async with AsyncClient(token) as client:
        tasks = [process_ticker(client, t, u) for t, u in tickers.items()]
        await asyncio.gather(*tasks)
    return results

@st.cache_data(ttl=55, show_spinner=False)
def scan_market(_token: str, _tickers_tuple: tuple) -> Dict[str, dict]:
    """
    Full market scan: fetch candles, compute indicators, and score each ticker.
    Uses async API to fetch all selected tickers concurrently.
    """
    tickers = dict(_tickers_tuple)
    lot_sizes = fetch_lot_sizes(_token, _tickers_tuple)
        
    return run_coro_sync(_scan_market_batch, _token, tickers, lot_sizes)


# ---------------------------------------------------------------------------
# Squeeze Scan 
# ---------------------------------------------------------------------------

async def _scan_squeeze_batch(token: str, tickers: dict) -> dict:
    results = {}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CANDLE_REQUESTS)

    async def process_ticker(client: AsyncClient, ticker: str, uid: str):
        for attempt in range(MAX_RETRIES):
            try:
                to_time = now()
                from_time = to_time - timedelta(days=SQUEEZE_CANDLES + 30)
                candles = []
                async with semaphore:
                    async for c in client.get_all_candles(
                        instrument_id=uid,
                        from_=from_time,
                        to=to_time,
                        interval=CandleInterval.CANDLE_INTERVAL_DAY,
                    ):
                        candles.append(c)

                if len(candles) < 30:
                    return

                df = prepare_candle_data(candles)
                df = calculate_indicators(df)
                metrics = calculate_squeeze_score(df, ATR_THRESHOLD)

                results[ticker] = {
                    "price": float(df.iloc[-1]["close"]),
                    "metrics": metrics,
                }
                return  # Success
            except Exception as e:
                if _is_retryable_api_error(e):
                    if attempt < MAX_RETRIES - 1:
                        wait = _retry_wait_seconds(e, attempt)
                        logger.warning(
                            f"Retryable squeeze error on {ticker}, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Squeeze scan error for {ticker}: exhausted {MAX_RETRIES} retries")
                else:
                    logger.error(f"Squeeze scan error for {ticker}: {e}")
                    return  # Non-retryable error

    async with AsyncClient(token) as client:
        tasks = [process_ticker(client, t, u) for t, u in tickers.items()]
        await asyncio.gather(*tasks)
    return results

@st.cache_data(ttl=55, show_spinner=False)
def scan_squeeze(_token: str, _tickers_tuple: tuple) -> Dict[str, dict]:
    """Scan all tickers for volatility squeeze metrics asynchronously."""
    tickers = dict(_tickers_tuple)
    return run_coro_sync(_scan_squeeze_batch, _token, tickers)
