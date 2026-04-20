"""
Vostok Web Terminal - Pure Math Indicator Engine
=================================================
Zero Streamlit dependencies. Can be tested and reused independently.

Provides: RSI, Bollinger Bands, MACD, ATR, OBV, Squeeze Detection,
Quantitative Confidence Scoring, and Signal Classification.
"""

from typing import Dict, Tuple, Optional
import pandas as pd
import numpy as np
import pandas_ta as ta

# ---------------------------------------------------------------------------
# Default Parameters
# ---------------------------------------------------------------------------
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD_DEV = 2
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_OVERSOLD_THRESHOLD = 30
BB_BUFFER = 1.0  # %
ATR_THRESHOLD = 0.7

# ---------------------------------------------------------------------------
# Candle Data Preparation
# ---------------------------------------------------------------------------

def prepare_candle_data(candles: list) -> pd.DataFrame:
    """Convert T-Bank API candle objects to a pandas DataFrame with OHLCV."""
    rows = []
    for c in candles:
        rows.append({
            "time": c.time,
            "open": float(c.open.units) + float(c.open.nano) / 1e9,
            "high": float(c.high.units) + float(c.high.nano) / 1e9,
            "low": float(c.low.units) + float(c.low.nano) / 1e9,
            "close": float(c.close.units) + float(c.close.nano) / 1e9,
            "volume": c.volume,
        })
    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    df.sort_index(inplace=True)
    return df

# ---------------------------------------------------------------------------
# Core Indicators
# ---------------------------------------------------------------------------

def calculate_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Relative Strength Index (Wilder smoothing via EMA)."""
    return ta.rsi(close, length=period)

def calculate_bollinger_bands(
    close: pd.Series,
    period: int = BB_PERIOD,
    std_dev: float = BB_STD_DEV,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, middle, lower) Bollinger Bands."""
    bb = ta.bbands(close, length=period, std=std_dev)
    if bb is None or bb.empty:
        return pd.Series(index=close.index), pd.Series(index=close.index), pd.Series(index=close.index)
    return bb.iloc[:, 2], bb.iloc[:, 1], bb.iloc[:, 0]  # Upper, Middle, Lower

def calculate_macd(
    close: pd.Series,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram)."""
    macd = ta.macd(close, fast=fast, slow=slow, signal=signal)
    if macd is None or macd.empty:
         return pd.Series(index=close.index), pd.Series(index=close.index), pd.Series(index=close.index)
    return macd.iloc[:, 0], macd.iloc[:, 2], macd.iloc[:, 1]  # Line, Signal, Histogram

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    return ta.atr(df["high"], df["low"], df["close"], length=period)

def calculate_ema(close: pd.Series, period: int = 20) -> pd.Series:
    """Exponential Moving Average."""
    return ta.ema(close, length=period)

def calculate_keltner_channels(
    df: pd.DataFrame, 
    period: int = 20, 
    atr_period: int = 10, 
    multiplier: float = 1.5
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, middle, lower) Keltner Channels."""
    ema = calculate_ema(df["close"], period)
    atr = calculate_atr(df, atr_period)
    upper = ema + (multiplier * atr)
    lower = ema - (multiplier * atr)
    return upper, ema, lower

def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    return ta.obv(df["close"], df["volume"])

# ---------------------------------------------------------------------------
# Composite Indicator Calculation
# ---------------------------------------------------------------------------

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Attach all technical indicators to the OHLCV DataFrame."""
    df = df.copy()
    df["RSI"] = calculate_rsi(df["close"])
    bb_u, bb_m, bb_l = calculate_bollinger_bands(df["close"])
    df["BB_UPPER"], df["BB_MIDDLE"], df["BB_LOWER"] = bb_u, bb_m, bb_l
    
    # New: Keltner for Squeeze
    kc_u, kc_m, kc_l = calculate_keltner_channels(df)
    df["KC_UPPER"], df["KC_MIDDLE"], df["KC_LOWER"] = kc_u, kc_m, kc_l
    
    # New: EMA for visuals
    df["EMA_20"] = calculate_ema(df["close"], 20)
    
    macd, sig, hist = calculate_macd(df["close"])
    df["MACD"], df["MACD_SIGNAL_LINE"], df["MACD_HISTOGRAM"] = macd, sig, hist
    df["ATR"] = calculate_atr(df)
    df["OBV"] = calculate_obv(df)
    df["CHANDELIER_EXIT"] = df["high"].rolling(window=22, min_periods=1).max() - (2.5 * df["ATR"])
    return df

# ---------------------------------------------------------------------------
# Buy-The-Dip Signal & MTF Confluence
# ---------------------------------------------------------------------------

def check_buy_signal(
    df: pd.DataFrame, 
    df_4h: Optional[pd.DataFrame] = None, 
    df_1h: Optional[pd.DataFrame] = None,
    bb_buffer: float = BB_BUFFER
) -> Tuple[bool, Dict[str, float], bool]:
    """
    Classic dip confluence: RSI < 30, price ≤ lower BB + buffer, MACD momentum improving.
    Returns: (is_triggered, values_dict, is_mtf_aplus_setup)
    """
    if len(df) < 2:
        return False, {}, False

    latest, previous = df.iloc[-1], df.iloc[-2]
    price = latest["close"]
    rsi = latest["RSI"]
    bb_lower = latest["BB_LOWER"]
    macd_hist = latest["MACD_HISTOGRAM"]
    prev_hist = previous["MACD_HISTOGRAM"]

    price_vs_bb = ((price - bb_lower) / bb_lower) * 100 if bb_lower else 0

    triggered = (
        rsi < RSI_OVERSOLD_THRESHOLD
        and price_vs_bb <= bb_buffer
        and macd_hist > prev_hist
    )

    # MTF Confluence Engine (A+ Setup)
    is_aplus = False
    if triggered and df_4h is not None and df_1h is not None and len(df_4h) > 0 and len(df_1h) > 0:
        latest_4h = df_4h.iloc[-1]
        latest_1h = df_1h.iloc[-1]
        
        # A+ Setup requires strong immediate momentum forming on lower timeframes:
        # e.g., MACD Histogram on 4H and 1H both positive or aggressively improving
        if latest_4h["MACD_HISTOGRAM"] > -0.1 and latest_1h["MACD_HISTOGRAM"] > 0 and latest_1h["RSI"] > 40:
            is_aplus = True

    vals = {
        "price": float(price),
        "rsi": float(rsi),
        "bb_lower": float(bb_lower),
        "bb_upper": float(latest["BB_UPPER"]),
        "macd": float(latest["MACD"]),
        "macd_histogram": float(macd_hist),
        "previous_macd_histogram": float(prev_hist),
        "price_vs_bb": float(price_vs_bb),
        "chandelier_exit": float(latest.get("CHANDELIER_EXIT", 0))
    }
    return triggered, vals, is_aplus

# ---------------------------------------------------------------------------
# Quantitative Confidence Scoring (0-100%)
# ---------------------------------------------------------------------------

def calculate_confidence_score(
    rsi: float,
    price: float,
    bb_lower: float,
    bb_upper: float,
    volume_ratio: float,
    macd_hist: float,
    macd_change: float,
) -> float:
    """
    Weighted composite score:
      RSI        30%  - max(0, 30 - RSI)
      BB Pos.    30%  - linear from upper (0) to lower (30)
      Volume     20%  - full if >150 % of 10d avg
      MACD       20%  - full if histogram positive & trending up
    """
    # RSI component (30 %)
    rsi_pts = min(30.0, max(0.0, 30.0 - rsi))

    # BB position component (30 %)
    bb_width = bb_upper - bb_lower
    if bb_width > 0:
        bb_position = (price - bb_lower) / bb_width  # 0 = lower, 1 = upper
        bb_pts = 30.0 * (1.0 - bb_position)
    else:
        bb_pts = 0.0
    bb_pts = max(0.0, min(30.0, bb_pts))

    # Volume component (20 %)
    if volume_ratio > 150:
        vol_pts = 20.0
    elif volume_ratio > 100:
        vol_pts = 10.0
    else:
        vol_pts = 0.0

    # MACD component (20 %)
    macd_pts = 20.0 if (macd_hist > 0 and macd_change > 0) else 0.0

    return min(100.0, max(0.0, rsi_pts + bb_pts + vol_pts + macd_pts))

# ---------------------------------------------------------------------------
# Signal Label & Sort Order
# ---------------------------------------------------------------------------

SIGNAL_SORT_ORDER = {"BUY (A+)": 0, "BUY": 1, "WATCH": 2, "NEUTRAL": 3, "WEAK": 4}

def get_signal_label(score: float, buy_signal: bool, is_aplus: bool = False) -> str:
    """Classify the confidence score into a signal tier."""
    if buy_signal or score >= 70:
        return "BUY (A+)" if is_aplus else "BUY"
    if score >= 40:
        return "WATCH"
    if score >= 20:
        return "NEUTRAL"
    return "WEAK"

# ---------------------------------------------------------------------------
# Squeeze Detection
# ---------------------------------------------------------------------------

def calculate_squeeze_score(
    df: pd.DataFrame, atr_threshold: float = ATR_THRESHOLD
) -> Dict[str, float]:
    """
    Pre-pump squeeze detection.
    Returns dict with: score, obv_trend, atr_ratio, is_squeeze, days_in_squeeze, is_breakout.
    """
    result = {
        "score": 100.0,
        "obv_trend": 0.0,
        "atr_ratio": 1.0,
        "is_squeeze": False,
        "days_in_squeeze": 0,
        "is_breakout": False,
    }
    if len(df) < 30:
        return result

    # BB Width percentile - direct rank on clean (non-NaN) data
    bb_width = (df["BB_UPPER"] - df["BB_LOWER"]) / df["BB_MIDDLE"]
    bb_width_clean = bb_width.dropna()

    if len(bb_width_clean) < 20:
        return result

    current_bw = float(bb_width_clean.iloc[-1])
    # Percentile: what fraction of historical BB widths are BELOW the current value
    percentile = float((bb_width_clean < current_bw).sum() / len(bb_width_clean) * 100)

    # Per-bar percentile series for days-in-squeeze counting
    def _pct_rank_at(i: int) -> float:
        """Percentile of bb_width at position i vs all prior values."""
        vals = bb_width_clean.iloc[: i + 1]
        if len(vals) < 10:
            return 100.0
        cur = float(vals.iloc[-1])
        return float((vals < cur).sum() / len(vals) * 100)

    pct_arr = np.array([_pct_rank_at(i) for i in range(len(bb_width_clean))])

    # OBV slope (5-period)
    obv = df["OBV"] if "OBV" in df.columns else calculate_obv(df)
    obv_slope = float(obv.diff(5).iloc[-1]) if len(obv) >= 6 else 0.0

    # ATR Volatility Ratio
    atr = df["ATR"] if "ATR" in df.columns else calculate_atr(df)
    atr_clean = atr.dropna()
    if len(atr_clean) < 10:
        return {**result, "score": percentile, "obv_trend": obv_slope}

    atr_50_avg = atr_clean.rolling(window=min(50, len(atr_clean)), min_periods=5).mean()
    atr_ratio_series = atr_clean / atr_50_avg
    atr_ratio = float(atr_ratio_series.iloc[-1]) if not pd.isna(atr_ratio_series.iloc[-1]) else 1.0

    # Breakout: Price > Upper BB AND Volume > 2× 10d avg
    avg_vol_10d = float(df["volume"].rolling(10).mean().iloc[-2]) if len(df) >= 11 else float(df["volume"].mean())
    is_breakout = bool(
        df["close"].iloc[-1] > df["BB_UPPER"].iloc[-1]
        and df["volume"].iloc[-1] > 2 * avg_vol_10d
    )

    # Squeeze flag: Standard definition -> BB inside KC
    # Also considering BB width percentile as a confirmatory metric
    is_squeeze = bool(
        df["BB_UPPER"].iloc[-1] <= df["KC_UPPER"].iloc[-1]
        and df["BB_LOWER"].iloc[-1] >= df["KC_LOWER"].iloc[-1]
    )

    # Count consecutive squeeze days
    days_in_squeeze = 0
    bb_up, bb_lo = df["BB_UPPER"].values, df["BB_LOWER"].values
    kc_up, kc_lo = df["KC_UPPER"].values, df["KC_LOWER"].values
    
    min_len = min(len(bb_up), len(kc_up))
    for k in range(1, min_len + 1):
        if (bb_up[-k] <= kc_up[-k] and bb_lo[-k] >= kc_lo[-k]):
            days_in_squeeze += 1
        else:
            break

    return {
        "score": percentile,
        "obv_trend": obv_slope,
        "atr_ratio": atr_ratio,
        "is_squeeze": is_squeeze,
        "days_in_squeeze": days_in_squeeze,
        "is_breakout": is_breakout,
    }


# ---------------------------------------------------------------------------
# Position Sizing (Risk Management)
# ---------------------------------------------------------------------------

def calculate_position_size(
    total_capital: float,
    risk_per_trade: float,
    stop_loss_percent: float,
    current_price: float,
    lot_size: int = 1,
) -> Dict[str, float]:
    """
    Risk-managed position sizing.

    Parameters use fractions: risk_per_trade=0.01 means 1 %.
    """
    risk_amount = total_capital * risk_per_trade
    raw_shares = risk_amount / (current_price * stop_loss_percent) if current_price * stop_loss_percent > 0 else 0
    lots = int(raw_shares / lot_size) if lot_size > 0 else 0
    shares = lots * lot_size
    stop_loss_price = current_price * (1 - stop_loss_percent)

    return {
        "shares": shares,
        "lots": lots,
        "lot_size": lot_size,
        "position_value": shares * current_price,
        "risk_amount": risk_amount,
        "entry_price": current_price,
        "stop_loss_price": stop_loss_price,
        "potential_loss": shares * (current_price - stop_loss_price),
    }
