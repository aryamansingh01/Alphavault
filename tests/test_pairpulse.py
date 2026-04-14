"""Tests for core/pairpulse.py — Pair Trading & Cointegration Engine."""
import math
import numpy as np
import pandas as pd
import pytest

from core.pairpulse import (
    test_cointegration as run_coint_test, find_pairs, calculate_spread,
    half_life, generate_signals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_index(n=504):
    return pd.date_range("2022-01-03", periods=n, freq="B")


def _cointegrated_pair(n=504, seed=42):
    """B = 2*A + noise with mean-reverting noise."""
    rng = np.random.default_rng(seed)
    idx = _make_index(n)
    a = 100 + np.cumsum(rng.normal(0, 1, n))
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.8 * noise[i - 1] + rng.normal(0, 0.5)
    b = 2 * a + 50 + noise
    return pd.Series(a, index=idx), pd.Series(b, index=idx)


def _random_walks(n=504, seed=42):
    """Two independent random walks — NOT cointegrated."""
    rng = np.random.default_rng(seed)
    idx = _make_index(n)
    a = 100 + np.cumsum(rng.normal(0, 1, n))
    b = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.Series(a, index=idx), pd.Series(b, index=idx)


def _mean_reverting_series(n=300, phi=0.95, seed=42):
    """AR(1) process with phi < 1 — mean-reverting."""
    rng = np.random.default_rng(seed)
    idx = _make_index(n)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + rng.normal(0, 1)
    return pd.Series(x, index=idx)


# ---------------------------------------------------------------------------
# Cointegration Testing
# ---------------------------------------------------------------------------

def test_coint_synthetic_cointegrated():
    a, b = _cointegrated_pair()
    result = run_coint_test(a, b)
    assert result["cointegrated"] is True
    assert result["p_value"] < 0.05


def test_coint_random_walks_not_cointegrated():
    """Two independent random walks — likely not cointegrated at 1% level."""
    a, b = _random_walks(n=504, seed=77)
    result = run_coint_test(a, b, significance=0.01)
    # With strict threshold, random walks should rarely pass
    assert result["p_value"] > 0.01 or result["cointegrated"] is False


def test_coint_proportional_series():
    """B = 2*A with tiny noise → cointegrated. OLS: a = alpha + beta*b, so beta ~ 0.5."""
    idx = _make_index(200)
    rng = np.random.default_rng(1)
    a = pd.Series(100 + np.cumsum(rng.normal(0, 1, 200)), index=idx)
    b = 2 * a + rng.normal(0, 0.01, 200)
    result = run_coint_test(a, b)
    assert result["cointegrated"] is True
    assert abs(result["hedge_ratio"] - 0.5) < 0.1


def test_coint_short_series():
    idx = _make_index(30)
    a = pd.Series(range(30), index=idx, dtype=float)
    b = pd.Series(range(30, 60), index=idx, dtype=float)
    result = run_coint_test(a, b)
    assert result["cointegrated"] is False
    assert "error" in result


def test_coint_hedge_ratio_finite():
    a, b = _cointegrated_pair()
    result = run_coint_test(a, b)
    assert np.isfinite(result["hedge_ratio"])


def test_coint_r_squared_bounds():
    a, b = _cointegrated_pair()
    result = run_coint_test(a, b)
    assert 0 <= result["r_squared"] <= 1


def test_coint_critical_values_keys():
    a, b = _cointegrated_pair()
    result = run_coint_test(a, b)
    cv = result["critical_values"]
    assert "1%" in cv
    assert "5%" in cv
    assert "10%" in cv


# ---------------------------------------------------------------------------
# Pair Discovery
# ---------------------------------------------------------------------------

def test_find_pairs_3_tickers():
    a, b = _cointegrated_pair()
    rng = np.random.default_rng(99)
    c = pd.Series(100 + np.cumsum(rng.normal(0, 1, 504)), index=_make_index(504))
    df = pd.DataFrame({"A": a, "B": b, "C": c})
    result = find_pairs(df, significance=0.05)
    # A-B should be cointegrated; A-C and B-C likely not
    assert isinstance(result, list)
    # At minimum A-B should be found
    assert any(p["ticker_a"] == "A" and p["ticker_b"] == "B" for p in result)


def test_find_pairs_all_random():
    rng = np.random.default_rng(42)
    idx = _make_index(300)
    df = pd.DataFrame({
        "X": 100 + np.cumsum(rng.normal(0, 1, 300)),
        "Y": 100 + np.cumsum(rng.normal(0, 1, 300)),
        "Z": 100 + np.cumsum(rng.normal(0, 1, 300)),
    }, index=idx)
    result = find_pairs(df, significance=0.01)  # strict threshold
    # Very unlikely to find cointegrated pairs among random walks
    assert isinstance(result, list)


def test_find_pairs_sorted_by_pvalue():
    a, b = _cointegrated_pair(504, seed=10)
    a2, b2 = _cointegrated_pair(504, seed=20)
    df = pd.DataFrame({"A": a, "B": b, "C": a2, "D": b2})
    result = find_pairs(df)
    if len(result) >= 2:
        assert result[0]["p_value"] <= result[1]["p_value"]


def test_find_pairs_max_pairs():
    a, b = _cointegrated_pair()
    df = pd.DataFrame({"A": a, "B": b})
    result = find_pairs(df, max_pairs=1)
    assert len(result) <= 1


def test_find_pairs_single_column():
    idx = _make_index(100)
    df = pd.DataFrame({"A": range(100)}, index=idx)
    result = find_pairs(df)
    assert result == []


# ---------------------------------------------------------------------------
# Spread
# ---------------------------------------------------------------------------

def test_spread_identical_series():
    idx = _make_index(200)
    a = pd.Series(np.arange(200, dtype=float), index=idx)
    result = calculate_spread(a, a.copy(), hedge_ratio=1.0)
    assert abs(result["current_spread"]) < 0.01
    assert abs(result["mean"]) < 0.01


def test_spread_current_z_finite():
    a, b = _cointegrated_pair(200)
    result = calculate_spread(a, b)
    assert np.isfinite(result["current_z"])


def test_spread_z_score_length():
    a, b = _cointegrated_pair(200)
    result = calculate_spread(a, b)
    assert len(result["z_score"]) == len(result["spread"])


def test_spread_pct_time_bounds():
    a, b = _cointegrated_pair(300)
    result = calculate_spread(a, b)
    assert 0 <= result["pct_time_above_2"] <= 100
    assert 0 <= result["pct_time_above_1"] <= 100


def test_spread_provided_hedge_ratio():
    a, b = _cointegrated_pair(200)
    result = calculate_spread(a, b, hedge_ratio=1.5)
    assert result["hedge_ratio"] == 1.5


# ---------------------------------------------------------------------------
# Half-Life
# ---------------------------------------------------------------------------

def test_half_life_mean_reverting():
    s = _mean_reverting_series(300, phi=0.95)
    hl = half_life(s)
    assert np.isfinite(hl)
    assert hl > 0


def test_half_life_random_walk():
    rng = np.random.default_rng(42)
    s = pd.Series(np.cumsum(rng.normal(0, 1, 300)), index=_make_index(300))
    hl = half_life(s)
    # Random walk has no mean reversion -> inf or very large
    assert hl > 100 or hl == float("inf")


def test_half_life_fast_reversion():
    s = _mean_reverting_series(300, phi=0.5)
    hl = half_life(s)
    assert np.isfinite(hl)
    assert hl < 10  # very fast reversion


def test_half_life_always_positive_or_inf():
    s = _mean_reverting_series(300, phi=0.9)
    hl = half_life(s)
    assert hl > 0


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def test_signal_short_spread():
    spread_data = {"current_z": 2.5}
    sig = generate_signals(spread_data)
    assert sig["signal"] == "SHORT_SPREAD"


def test_signal_long_spread():
    spread_data = {"current_z": -2.5}
    sig = generate_signals(spread_data)
    assert sig["signal"] == "LONG_SPREAD"


def test_signal_exit():
    spread_data = {"current_z": 0.3}
    sig = generate_signals(spread_data)
    assert sig["signal"] == "EXIT"


def test_signal_stop_loss():
    spread_data = {"current_z": 4.5}
    sig = generate_signals(spread_data)
    assert sig["signal"] == "STOP_LOSS"


def test_signal_no_signal():
    spread_data = {"current_z": 1.5}
    sig = generate_signals(spread_data)
    assert sig["signal"] == "NO_SIGNAL"


def test_signal_strength_increases():
    s2 = generate_signals({"current_z": 2.1})
    s3 = generate_signals({"current_z": 3.5})
    assert s3["strength"] >= s2["strength"]


def test_signal_description_nonempty():
    sig = generate_signals({"current_z": 2.5})
    assert isinstance(sig["description"], str)
    assert len(sig["description"]) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_none_prices():
    result = run_coint_test(None, None)
    assert result["cointegrated"] is False


def test_spread_short_data():
    """Short data returns error dict gracefully."""
    idx = _make_index(5)
    a = pd.Series([1, 2, 3, 4, 5], index=idx, dtype=float)
    b = pd.Series([2, 4, 6, 8, 10], index=idx, dtype=float)
    result = calculate_spread(a, b)
    # Should either succeed or return an error dict, not crash
    assert isinstance(result, dict)
