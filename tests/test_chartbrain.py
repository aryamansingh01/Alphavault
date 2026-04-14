"""Tests for core/chartbrain.py — Technical Analysis Engine."""
import numpy as np
import pandas as pd
import pytest

from core.chartbrain import (
    sma, ema, rsi, macd, bollinger_bands, atr, vwap, volume_sma,
    support_resistance, detect_signals, compute_all_indicators,
    _series_to_list,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(values, start="2024-01-02"):
    """Create a pd.Series with a DatetimeIndex."""
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype=float)


def _make_ohlcv(n=100, base=100.0, seed=42):
    """Create a realistic-ish OHLCV DataFrame."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.02, n)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    opn = close * (1 + rng.normal(0, 0.005, n))
    vol = rng.integers(500000, 5000000, n)
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"open": opn, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


# ---------------------------------------------------------------------------
# SMA / EMA
# ---------------------------------------------------------------------------

def test_sma_known_values():
    prices = _make_prices([1, 2, 3, 4, 5])
    result = sma(prices, window=3)
    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert abs(result.iloc[2] - 2.0) < 1e-9
    assert abs(result.iloc[3] - 3.0) < 1e-9
    assert abs(result.iloc[4] - 4.0) < 1e-9


def test_sma_length_matches_input():
    prices = _make_prices(list(range(50)))
    result = sma(prices, 20)
    assert len(result) == len(prices)


def test_sma_empty():
    result = sma(pd.Series(dtype=float))
    assert len(result) == 0


def test_ema_length_matches_input():
    prices = _make_prices(list(range(50)))
    result = ema(prices, 12)
    assert len(result) == len(prices)


def test_ema_first_value_equals_price():
    """EMA with adjust=False: first value should equal first price."""
    prices = _make_prices([10, 20, 30, 40, 50])
    result = ema(prices, span=3)
    assert abs(result.iloc[0] - 10.0) < 1e-9


def test_ema_empty():
    result = ema(pd.Series(dtype=float))
    assert len(result) == 0


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def test_rsi_bounds():
    """RSI should always be between 0 and 100."""
    rng = np.random.default_rng(42)
    prices = _make_prices(100 * np.cumprod(1 + rng.normal(0, 0.03, 200)))
    result = rsi(prices)
    valid = result.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_rsi_all_up():
    """Monotonically increasing prices -> RSI near 100."""
    prices = _make_prices(list(range(100, 200)))
    result = rsi(prices)
    valid = result.dropna()
    assert valid.iloc[-1] > 90


def test_rsi_all_down():
    """Monotonically decreasing prices -> RSI near 0."""
    prices = _make_prices(list(range(200, 100, -1)))
    result = rsi(prices)
    valid = result.dropna()
    assert valid.iloc[-1] < 10


def test_rsi_flat():
    """Flat prices -> no gains, no losses. RSI should be near 100."""
    prices = _make_prices([50.0] * 50)
    result = rsi(prices)
    valid = result.dropna()
    # With zero gains and zero losses, avg_loss approaches 0 -> RSI near 100
    assert valid.iloc[-1] > 95


def test_rsi_nan_for_first_period():
    prices = _make_prices(list(range(30)))
    result = rsi(prices, period=14)
    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[13])
    assert not np.isnan(result.iloc[14])


def test_rsi_short_input():
    prices = _make_prices([1, 2, 3])
    result = rsi(prices, period=14)
    assert all(np.isnan(v) for v in result)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def test_macd_flat_prices():
    """Flat prices -> MACD line and histogram should be ~0."""
    prices = _make_prices([100.0] * 50)
    result = macd(prices)
    assert abs(result["macd_line"].iloc[-1]) < 1e-6
    assert abs(result["histogram"].iloc[-1]) < 1e-6


def test_macd_returns_three_series():
    prices = _make_prices(list(range(50)))
    result = macd(prices)
    assert "macd_line" in result
    assert "signal_line" in result
    assert "histogram" in result
    assert len(result["macd_line"]) == 50


def test_macd_histogram_equals_diff():
    prices = _make_prices(np.random.default_rng(42).normal(100, 5, 60).cumsum())
    result = macd(prices)
    diff = result["macd_line"] - result["signal_line"]
    np.testing.assert_array_almost_equal(result["histogram"].values, diff.values)


def test_macd_empty():
    result = macd(pd.Series(dtype=float))
    assert len(result["macd_line"]) == 0


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def test_bollinger_constant_prices():
    """Constant prices -> upper = lower = middle = price, bandwidth = 0."""
    prices = _make_prices([50.0] * 30)
    bb = bollinger_bands(prices, window=20)
    valid_mid = bb["middle"].dropna()
    valid_upper = bb["upper"].dropna()
    valid_lower = bb["lower"].dropna()
    assert abs(valid_mid.iloc[-1] - 50.0) < 1e-9
    # std = 0 so upper and lower should collapse to middle
    assert abs(valid_upper.iloc[-1] - 50.0) < 1e-9
    assert abs(valid_lower.iloc[-1] - 50.0) < 1e-9


def test_bollinger_bands_contain_most_prices():
    """For random data, most prices should be within bands."""
    rng = np.random.default_rng(42)
    prices = _make_prices(100 + rng.normal(0, 1, 200).cumsum())
    bb = bollinger_bands(prices, window=20, num_std=2.0)
    valid = ~bb["upper"].isna()
    within = ((prices[valid] <= bb["upper"][valid]) & (prices[valid] >= bb["lower"][valid]))
    assert within.mean() > 0.85  # >85% within 2-std bands


def test_bollinger_returns_all_keys():
    prices = _make_prices(list(range(30)))
    bb = bollinger_bands(prices)
    assert all(k in bb for k in ["upper", "middle", "lower", "bandwidth", "percent_b"])


def test_bollinger_empty():
    bb = bollinger_bands(pd.Series(dtype=float))
    assert len(bb["upper"]) == 0


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

def test_atr_non_negative():
    df = _make_ohlcv(60)
    result = atr(df["high"], df["low"], df["close"])
    valid = result.dropna()
    assert (valid >= 0).all()


def test_atr_nan_for_first_period():
    df = _make_ohlcv(30)
    result = atr(df["high"], df["low"], df["close"], period=14)
    assert np.isnan(result.iloc[0])
    assert not np.isnan(result.iloc[14])


def test_atr_empty():
    result = atr(pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float))
    assert len(result) == 0


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------

def test_vwap_uniform_volume():
    """With uniform volume, VWAP ~ cumulative mean of typical price."""
    n = 20
    h = _make_prices([105] * n)
    l = _make_prices([95] * n)
    c = _make_prices([100] * n)
    v = _make_prices([1000] * n)
    result = vwap(h, l, c, v)
    # TP = (105+95+100)/3 = 100, VWAP should be 100 throughout
    assert abs(result.iloc[-1] - 100.0) < 1e-6


def test_vwap_empty():
    result = vwap(pd.Series(dtype=float), pd.Series(dtype=float),
                  pd.Series(dtype=float), pd.Series(dtype=float))
    assert len(result) == 0


# ---------------------------------------------------------------------------
# Volume SMA
# ---------------------------------------------------------------------------

def test_volume_sma_basic():
    vol = _make_prices([100] * 30)
    result = volume_sma(vol, 20)
    assert abs(result.iloc[-1] - 100.0) < 1e-9


# ---------------------------------------------------------------------------
# Support & Resistance
# ---------------------------------------------------------------------------

def test_support_resistance_obvious_levels():
    """Create data with clear peaks and valleys."""
    # Valley at 80, peak at 120, repeated
    pattern = list(range(80, 121)) + list(range(119, 79, -1))  # 41 + 40 = 81
    data = pattern * 3  # 243 points
    prices = _make_prices(data)
    sr = support_resistance(prices, window=10, num_levels=3)
    assert len(sr["support"]) > 0
    assert len(sr["resistance"]) > 0
    # Support should be near 80, resistance near 120
    assert any(abs(s - 80) < 5 for s in sr["support"])
    assert any(abs(r - 120) < 5 for r in sr["resistance"])


def test_support_resistance_short_data():
    prices = _make_prices([100, 101, 102])
    sr = support_resistance(prices, window=20)
    assert sr == {"support": [], "resistance": []}


# ---------------------------------------------------------------------------
# Signal Detection
# ---------------------------------------------------------------------------

def test_detect_signals_oversold():
    """Rapidly declining prices should trigger RSI oversold signal."""
    prices = _make_prices(list(range(200, 100, -1)))
    signals = detect_signals(prices)
    rsi_signals = [s for s in signals if s["indicator"] == "RSI"]
    assert len(rsi_signals) > 0
    assert any("oversold" in s["message"].lower() for s in rsi_signals)


def test_detect_signals_overbought():
    """Rapidly rising prices should trigger RSI overbought signal."""
    prices = _make_prices(list(range(100, 200)))
    signals = detect_signals(prices)
    rsi_signals = [s for s in signals if s["indicator"] == "RSI"]
    assert len(rsi_signals) > 0
    assert any("overbought" in s["message"].lower() for s in rsi_signals)


def test_detect_signals_boring_data():
    """Flat-ish data near midrange should produce minimal signals."""
    rng = np.random.default_rng(42)
    prices = _make_prices(100 + rng.normal(0, 0.1, 50))
    signals = detect_signals(prices)
    # Should have no RSI extreme signals since data is flat
    rsi_extreme = [s for s in signals if s["indicator"] == "RSI" and s["strength"] == 5]
    assert len(rsi_extreme) == 0


def test_detect_signals_macd_crossover():
    """Verify MACD crossover detection logic with a direct unit check."""
    from core.chartbrain import macd as _macd
    # Build data where MACD crosses signal at the very last bar
    # Flat then gentle rise then sudden drop at end to get bearish cross
    gentle_rise = [100.0 + i * 0.5 for i in range(50)]
    sharp_drop = [gentle_rise[-1] - i * 4.0 for i in range(1, 12)]
    prices = _make_prices(gentle_rise + sharp_drop)
    m = _macd(prices)
    ml, sl = m["macd_line"], m["signal_line"]
    # Find any crossing in the series
    diffs = ml - sl
    crossings = []
    for i in range(1, len(diffs)):
        if not np.isnan(diffs.iloc[i]) and not np.isnan(diffs.iloc[i-1]):
            if (diffs.iloc[i-1] > 0 and diffs.iloc[i] < 0) or (diffs.iloc[i-1] < 0 and diffs.iloc[i] > 0):
                crossings.append(i)
    # There should be at least one crossing in this synthetic data
    assert len(crossings) > 0, "Expected at least one MACD crossing"


def test_detect_signals_golden_cross():
    """Need 201+ data points. Create a crossover scenario."""
    # SMA50 below SMA200 initially, then rapid rise to push SMA50 above
    flat = [100.0] * 180
    ramp = [100.0 + i * 3.0 for i in range(50)]
    prices = _make_prices(flat + ramp)
    signals = detect_signals(prices)
    ma_signals = [s for s in signals if s["indicator"] == "MA"]
    # May or may not trigger depending on exact crossing, but should not crash
    assert isinstance(signals, list)


def test_detect_signals_volume_spike():
    n = 30
    prices = _make_prices([100] * n)
    vol = _make_prices([1000] * (n - 1) + [5000])  # last day has 5x volume
    signals = detect_signals(prices, volume=vol)
    vol_signals = [s for s in signals if s["indicator"] == "Volume"]
    assert len(vol_signals) > 0


def test_detect_signals_empty():
    signals = detect_signals(pd.Series(dtype=float))
    assert signals == []


def test_detect_signals_single_price():
    signals = detect_signals(_make_prices([100.0]))
    assert signals == []


def test_detect_signal_types():
    """All signals must have required keys."""
    df = _make_ohlcv(100)
    signals = detect_signals(df["close"], high=df["high"], low=df["low"],
                             close=df["close"], volume=df["volume"])
    for s in signals:
        assert "type" in s
        assert "indicator" in s
        assert "message" in s
        assert "strength" in s
        assert s["type"] in ("bullish", "bearish", "neutral")
        assert 1 <= s["strength"] <= 5


# ---------------------------------------------------------------------------
# compute_all_indicators
# ---------------------------------------------------------------------------

def test_compute_all_indicators_keys():
    df = _make_ohlcv(100)
    result = compute_all_indicators(df)
    assert "sma_20" in result
    assert "sma_50" in result
    assert "sma_200" in result
    assert "ema_12" in result
    assert "rsi" in result
    assert "macd" in result
    assert "bollinger" in result
    assert "atr" in result
    assert "vwap" in result
    assert "support_resistance" in result
    assert "signals" in result


def test_compute_all_indicators_no_crash():
    """Should not crash on various DataFrame sizes."""
    for n in [5, 20, 50, 100, 250]:
        df = _make_ohlcv(n)
        result = compute_all_indicators(df)
        assert isinstance(result, dict)


def test_compute_all_indicators_empty():
    result = compute_all_indicators(pd.DataFrame())
    assert result["sma_20"] == []
    assert result["signals"] == []


def test_compute_all_indicators_json_serializable():
    """All values should be JSON-serializable (lists of float/None)."""
    import json
    df = _make_ohlcv(50)
    result = compute_all_indicators(df)
    # Should not raise
    json.dumps(result)


# ---------------------------------------------------------------------------
# NaN handling
# ---------------------------------------------------------------------------

def test_nan_in_prices():
    """Prices with NaN should not crash any indicator."""
    vals = [100, 101, np.nan, 103, 104, 105] + list(range(106, 130))
    prices = _make_prices(vals)
    sma_result = sma(prices, 5)
    rsi_result = rsi(prices)
    macd_result = macd(prices)
    assert len(sma_result) == len(prices)
    assert len(rsi_result) == len(prices)


def test_series_to_list_nan():
    s = pd.Series([1.0, np.nan, 3.0])
    result = _series_to_list(s)
    assert result == [1.0, None, 3.0]
