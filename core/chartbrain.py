"""
Technical Analysis Engine.
Computes indicators, detects signals, and identifies support/resistance levels.
All functions are pure computation — no data fetching or HTTP.
"""
import numpy as np
import pandas as pd
from core.sanitize import sanitize_returns, require_min_length


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def sma(prices: pd.Series, window: int = 20) -> pd.Series:
    """Simple Moving Average.
    SMA(t) = (1/n) * sum(P(t-i)) for i=0..n-1
    Returns Series same length as prices, with NaN for first (window-1) values."""
    if prices is None or len(prices) == 0:
        return pd.Series(dtype=float)
    return prices.rolling(window=window, min_periods=window).mean()


def ema(prices: pd.Series, span: int = 12) -> pd.Series:
    """Exponential Moving Average.
    EMA(t) = alpha * P(t) + (1-alpha) * EMA(t-1), where alpha = 2/(span+1)
    Returns Series same length as prices."""
    if prices is None or len(prices) == 0:
        return pd.Series(dtype=float)
    return prices.ewm(span=span, adjust=False).mean()


# ---------------------------------------------------------------------------
# Momentum Indicators
# ---------------------------------------------------------------------------

def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing.
    Always bounded 0-100. Returns NaN for first `period` values."""
    if prices is None or len(prices) < period + 1:
        return pd.Series([np.nan] * (len(prices) if prices is not None else 0), dtype=float)

    delta = prices.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    # Wilder's smoothing
    avg_gain = np.full(len(prices), np.nan)
    avg_loss = np.full(len(prices), np.nan)

    # First average: simple mean of first `period` values
    avg_gain[period] = gains.iloc[1:period + 1].mean()
    avg_loss[period] = losses.iloc[1:period + 1].mean()

    for i in range(period + 1, len(prices)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains.iloc[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses.iloc[i]) / period

    rs = np.where(avg_loss == 0, 100.0, avg_gain / avg_loss)
    rsi_vals = np.where(np.isnan(avg_gain), np.nan, 100.0 - (100.0 / (1.0 + rs)))
    return pd.Series(rsi_vals, index=prices.index, dtype=float)


def macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """Moving Average Convergence Divergence.
    MACD Line = EMA(fast) - EMA(slow)
    Signal Line = EMA(signal) of MACD Line
    Histogram = MACD Line - Signal Line

    Returns: {"macd_line": Series, "signal_line": Series, "histogram": Series}"""
    if prices is None or len(prices) == 0:
        empty = pd.Series(dtype=float)
        return {"macd_line": empty, "signal_line": empty, "histogram": empty}

    ema_fast = ema(prices, span=fast)
    ema_slow = ema(prices, span=slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return {"macd_line": macd_line, "signal_line": signal_line, "histogram": histogram}


# ---------------------------------------------------------------------------
# Volatility Indicators
# ---------------------------------------------------------------------------

def bollinger_bands(prices: pd.Series, window: int = 20, num_std: float = 2.0) -> dict:
    """Bollinger Bands.
    Middle = SMA(window)
    Upper = Middle + num_std * rolling_std(window)
    Lower = Middle - num_std * rolling_std(window)
    Bandwidth = (Upper - Lower) / Middle * 100
    %B = (Price - Lower) / (Upper - Lower)"""
    if prices is None or len(prices) == 0:
        empty = pd.Series(dtype=float)
        return {"upper": empty, "middle": empty, "lower": empty,
                "bandwidth": empty, "percent_b": empty}

    middle = sma(prices, window)
    rolling_std = prices.rolling(window=window, min_periods=window).std()
    upper = middle + num_std * rolling_std
    lower = middle - num_std * rolling_std
    bandwidth = ((upper - lower) / middle) * 100
    diff = upper - lower
    percent_b = (prices - lower) / diff.replace(0, np.nan)

    return {"upper": upper, "middle": middle, "lower": lower,
            "bandwidth": bandwidth, "percent_b": percent_b}


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range using Wilder's smoothing.
    True Range = max(H-L, |H-Cprev|, |L-Cprev|)
    Returns Series with NaN for first `period` values."""
    if high is None or len(high) < 2:
        return pd.Series(dtype=float)

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_vals = np.full(len(tr), np.nan)
    if len(tr) > period:
        atr_vals[period] = tr.iloc[1:period + 1].mean()
        for i in range(period + 1, len(tr)):
            atr_vals[i] = (atr_vals[i - 1] * (period - 1) + tr.iloc[i]) / period

    return pd.Series(atr_vals, index=high.index, dtype=float)


# ---------------------------------------------------------------------------
# Volume Indicators
# ---------------------------------------------------------------------------

def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Volume Weighted Average Price.
    Typical Price = (H + L + C) / 3
    VWAP = cumulative(TP * Volume) / cumulative(Volume)"""
    if high is None or len(high) == 0:
        return pd.Series(dtype=float)

    tp = (high + low + close) / 3.0
    cum_tp_vol = (tp * volume).cumsum()
    cum_vol = volume.cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)


def volume_sma(volume: pd.Series, window: int = 20) -> pd.Series:
    """Simple moving average of volume."""
    if volume is None or len(volume) == 0:
        return pd.Series(dtype=float)
    return volume.rolling(window=window, min_periods=window).mean()


# ---------------------------------------------------------------------------
# Support & Resistance
# ---------------------------------------------------------------------------

def support_resistance(prices: pd.Series, window: int = 20, num_levels: int = 3) -> dict:
    """Detect support and resistance levels using local minima/maxima.
    1. Find local minima (support) and maxima (resistance) within +/-window
    2. Cluster nearby levels (within 1% of each other) and average
    3. Return top num_levels strongest levels for each"""
    if prices is None or len(prices) < window * 2 + 1:
        return {"support": [], "resistance": []}

    arr = prices.values
    n = len(arr)
    supports = []
    resistances = []

    for i in range(window, n - window):
        local_window = arr[i - window:i + window + 1]
        if arr[i] == local_window.min():
            supports.append(float(arr[i]))
        if arr[i] == local_window.max():
            resistances.append(float(arr[i]))

    supports = _cluster_levels(supports, num_levels)
    resistances = _cluster_levels(resistances, num_levels)

    return {"support": sorted(supports), "resistance": sorted(resistances)}


def _cluster_levels(levels: list, num_levels: int) -> list:
    """Cluster nearby price levels (within 1%) and return top num_levels by frequency."""
    if not levels:
        return []

    levels = sorted(levels)
    clusters = []
    current_cluster = [levels[0]]

    for i in range(1, len(levels)):
        if levels[i] <= current_cluster[-1] * 1.01:
            current_cluster.append(levels[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [levels[i]]
    clusters.append(current_cluster)

    # Sort by cluster size (frequency), take top num_levels
    clusters.sort(key=lambda c: len(c), reverse=True)
    result = [float(np.mean(c)) for c in clusters[:num_levels]]
    return result


# ---------------------------------------------------------------------------
# Signal Detection
# ---------------------------------------------------------------------------

def detect_signals(prices: pd.Series, high: pd.Series = None, low: pd.Series = None,
                   close: pd.Series = None, volume: pd.Series = None) -> list:
    """Detect trading signals from technical indicators.
    Returns list of signal dicts. Can be empty if no signals detected."""
    if prices is None or len(prices) < 2:
        return []

    signals = []
    close_prices = close if close is not None else prices

    # RSI signals
    if len(prices) > 14:
        rsi_vals = rsi(close_prices)
        last_rsi = rsi_vals.iloc[-1]
        if not np.isnan(last_rsi):
            if last_rsi < 20:
                signals.append({"type": "bullish", "indicator": "RSI",
                                "message": f"RSI extreme oversold at {last_rsi:.1f}", "strength": 5})
            elif last_rsi < 30:
                signals.append({"type": "bullish", "indicator": "RSI",
                                "message": f"RSI oversold at {last_rsi:.1f}", "strength": 3})
            elif last_rsi > 80:
                signals.append({"type": "bearish", "indicator": "RSI",
                                "message": f"RSI extreme overbought at {last_rsi:.1f}", "strength": 5})
            elif last_rsi > 70:
                signals.append({"type": "bearish", "indicator": "RSI",
                                "message": f"RSI overbought at {last_rsi:.1f}", "strength": 3})

    # MACD crossover signals
    if len(prices) > 26:
        m = macd(close_prices)
        ml = m["macd_line"]
        sl = m["signal_line"]
        if len(ml) >= 2 and not np.isnan(ml.iloc[-1]) and not np.isnan(sl.iloc[-1]):
            curr_above = ml.iloc[-1] > sl.iloc[-1]
            prev_above = ml.iloc[-2] > sl.iloc[-2]
            if curr_above and not prev_above:
                signals.append({"type": "bullish", "indicator": "MACD",
                                "message": "MACD bullish crossover", "strength": 3})
            elif not curr_above and prev_above:
                signals.append({"type": "bearish", "indicator": "MACD",
                                "message": "MACD bearish crossover", "strength": 3})

    # Golden Cross / Death Cross (SMA 50 vs 200)
    if len(prices) >= 201:
        sma50 = sma(close_prices, 50)
        sma200 = sma(close_prices, 200)
        if (not np.isnan(sma50.iloc[-1]) and not np.isnan(sma200.iloc[-1])
                and not np.isnan(sma50.iloc[-2]) and not np.isnan(sma200.iloc[-2])):
            curr_above = sma50.iloc[-1] > sma200.iloc[-1]
            prev_above = sma50.iloc[-2] > sma200.iloc[-2]
            if curr_above and not prev_above:
                signals.append({"type": "bullish", "indicator": "MA",
                                "message": "Golden Cross (50 > 200 SMA)", "strength": 5})
            elif not curr_above and prev_above:
                signals.append({"type": "bearish", "indicator": "MA",
                                "message": "Death Cross (50 < 200 SMA)", "strength": 5})

    # Bollinger Band signals
    if len(prices) > 20:
        bb = bollinger_bands(close_prices)
        last_bw = bb["bandwidth"].iloc[-1]
        last_price = close_prices.iloc[-1]
        last_upper = bb["upper"].iloc[-1]
        last_lower = bb["lower"].iloc[-1]

        if not np.isnan(last_bw):
            bw_valid = bb["bandwidth"].dropna()
            if len(bw_valid) > 10:
                p10 = bw_valid.quantile(0.10)
                if last_bw < p10:
                    signals.append({"type": "neutral", "indicator": "Bollinger",
                                    "message": "Bollinger squeeze — breakout imminent", "strength": 2})

        if not np.isnan(last_upper) and last_price > last_upper:
            signals.append({"type": "bullish", "indicator": "Bollinger",
                            "message": "Price above upper Bollinger Band", "strength": 3})
        if not np.isnan(last_lower) and last_price < last_lower:
            signals.append({"type": "bearish", "indicator": "Bollinger",
                            "message": "Price below lower Bollinger Band", "strength": 3})

    # Volume spike
    if volume is not None and len(volume) > 20:
        vol_avg = volume_sma(volume, 20)
        last_vol = volume.iloc[-1]
        last_avg = vol_avg.iloc[-1]
        if not np.isnan(last_avg) and last_avg > 0:
            ratio = last_vol / last_avg
            if ratio > 2.0:
                signals.append({"type": "neutral", "indicator": "Volume",
                                "message": f"Volume spike ({ratio:.1f}x average)", "strength": 2})

    return signals


# ---------------------------------------------------------------------------
# Convenience: all indicators at once
# ---------------------------------------------------------------------------

def _series_to_list(s: pd.Series) -> list:
    """Convert Series to list, replacing NaN with None for JSON compatibility."""
    if s is None or (isinstance(s, pd.Series) and s.empty):
        return []
    return [None if pd.isna(v) else float(v) for v in s]


def compute_all_indicators(ohlcv: pd.DataFrame) -> dict:
    """Compute all indicators from an OHLCV DataFrame.
    Expects DataFrame with columns: open, high, low, close, volume"""
    if ohlcv is None or ohlcv.empty:
        return {
            "sma_20": [], "sma_50": [], "sma_200": [],
            "ema_12": [], "ema_26": [],
            "rsi": [],
            "macd": {"macd_line": [], "signal_line": [], "histogram": []},
            "bollinger": {"upper": [], "middle": [], "lower": [], "bandwidth": [], "percent_b": []},
            "atr": [], "vwap": [],
            "support_resistance": {"support": [], "resistance": []},
            "signals": [],
        }

    c = ohlcv["close"] if "close" in ohlcv.columns else pd.Series(dtype=float)
    h = ohlcv["high"] if "high" in ohlcv.columns else None
    l = ohlcv["low"] if "low" in ohlcv.columns else None
    v = ohlcv["volume"] if "volume" in ohlcv.columns else None

    m = macd(c)
    bb = bollinger_bands(c)

    result = {
        "sma_20": _series_to_list(sma(c, 20)),
        "sma_50": _series_to_list(sma(c, 50)),
        "sma_200": _series_to_list(sma(c, 200)),
        "ema_12": _series_to_list(ema(c, 12)),
        "ema_26": _series_to_list(ema(c, 26)),
        "rsi": _series_to_list(rsi(c)),
        "macd": {
            "macd_line": _series_to_list(m["macd_line"]),
            "signal_line": _series_to_list(m["signal_line"]),
            "histogram": _series_to_list(m["histogram"]),
        },
        "bollinger": {
            "upper": _series_to_list(bb["upper"]),
            "middle": _series_to_list(bb["middle"]),
            "lower": _series_to_list(bb["lower"]),
            "bandwidth": _series_to_list(bb["bandwidth"]),
            "percent_b": _series_to_list(bb["percent_b"]),
        },
        "atr": _series_to_list(atr(h, l, c) if h is not None and l is not None else pd.Series(dtype=float)),
        "vwap": _series_to_list(vwap(h, l, c, v) if h is not None and l is not None and v is not None else pd.Series(dtype=float)),
        "support_resistance": support_resistance(c),
        "signals": detect_signals(c, high=h, low=l, close=c, volume=v),
    }

    return result
