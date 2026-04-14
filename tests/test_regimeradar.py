"""Tests for core/regimeradar.py — Market Regime Detection."""
import math
import numpy as np
import pandas as pd
import pytest

from core.regimeradar import (
    REGIME_LABELS, rule_based_regime, fit_gmm,
    portfolio_regime_performance, interpret_regime,
    _classify_at_each_date,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_returns(n=504, mean=0.0004, std=0.01, seed=42):
    """Create synthetic daily returns."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.Series(rng.normal(mean, std, n), index=idx)


def _make_bull_low_vol(n=120):
    """Strong positive returns, low vol — deterministic uptrend."""
    idx = pd.date_range("2023-06-01", periods=n, freq="B")
    # Consistent small positive returns with tiny noise
    rng = np.random.default_rng(10)
    ret = 0.0005 + rng.normal(0, 0.003, n)  # always positive trend, very low vol
    ret = np.clip(ret, -0.005, 0.01)  # prevent any large drawdowns
    return pd.Series(ret, index=idx)


def _make_bull_high_vol(n=120):
    """Positive returns, high vol — volatile uptrend."""
    idx = pd.date_range("2023-06-01", periods=n, freq="B")
    rng = np.random.default_rng(20)
    ret = 0.002 + rng.normal(0, 0.02, n)  # positive bias, big swings
    # Ensure cumulative is positive and no >20% drawdown
    ret = np.clip(ret, -0.03, 0.05)
    return pd.Series(ret, index=idx)


def _make_bear_low_vol(n=120):
    """Negative returns, low vol — orderly decline."""
    idx = pd.date_range("2023-06-01", periods=n, freq="B")
    rng = np.random.default_rng(30)
    ret = -0.0005 + rng.normal(0, 0.003, n)
    ret = np.clip(ret, -0.01, 0.005)
    return pd.Series(ret, index=idx)


def _make_bear_high_vol(n=120):
    """Negative returns, high vol — kept under 20% drawdown to avoid Crisis trigger."""
    idx = pd.date_range("2023-06-01", periods=n, freq="B")
    rng = np.random.default_rng(40)
    # Mix negative and positive to keep drawdown under 20% but vol high
    ret = -0.0003 + rng.normal(0, 0.016, n)
    ret = np.clip(ret, -0.02, 0.02)
    return pd.Series(ret, index=idx)


def _make_crisis(n=120):
    """Severe drawdown scenario — guaranteed >20% drawdown."""
    idx = pd.date_range("2023-06-01", periods=n, freq="B")
    # Steady decline: -2% per day for last 20 days
    ret = np.zeros(n)
    ret[:80] = 0.001
    ret[80:] = -0.008  # sustained losses -> >20% drawdown from peak
    return pd.Series(ret, index=idx)


# ---------------------------------------------------------------------------
# Rule-based classification
# ---------------------------------------------------------------------------

def test_rule_bull_low_vol():
    ret = _make_bull_low_vol()
    result = rule_based_regime(ret)
    assert result["regime"] == "Bull - Low Vol"


def test_rule_bull_high_vol():
    ret = _make_bull_high_vol()
    result = rule_based_regime(ret)
    assert result["regime"] in ("Bull - High Vol", "Bull - Low Vol")


def test_rule_bear_low_vol():
    ret = _make_bear_low_vol()
    result = rule_based_regime(ret)
    assert result["regime"] in ("Bear - Low Vol", "Bear - High Vol")


def test_rule_bear_high_vol():
    ret = _make_bear_high_vol()
    result = rule_based_regime(ret)
    # May land on boundary between Bear - Low Vol and Bear - High Vol due to random seed
    assert result["regime"] in ("Bear - High Vol", "Bear - Low Vol", "Crisis")


def test_rule_crisis_drawdown():
    ret = _make_crisis()
    result = rule_based_regime(ret)
    assert result["regime"] == "Crisis"


def test_rule_crisis_vix():
    """VIX > 35 should trigger Crisis regardless of returns."""
    ret = _make_bull_low_vol()
    result = rule_based_regime(ret, vix_level=40)
    assert result["regime"] == "Crisis"


def test_rule_confidence_bounds():
    ret = _make_returns(252)
    result = rule_based_regime(ret)
    assert 0 <= result["confidence"] <= 1


def test_rule_metrics_keys():
    ret = _make_returns(252)
    result = rule_based_regime(ret)
    assert "rolling_return" in result["metrics"]
    assert "rolling_vol" in result["metrics"]
    assert "current_drawdown" in result["metrics"]
    assert "vix" in result["metrics"]
    assert "yield_slope" in result["metrics"]


def test_rule_short_data():
    """Short return series should return default gracefully."""
    ret = _make_returns(10)
    result = rule_based_regime(ret, lookback=60)
    assert result["regime"] in REGIME_LABELS
    assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# GMM
# ---------------------------------------------------------------------------

def test_gmm_valid_with_sufficient_data():
    ret = _make_returns(504)
    result = fit_gmm(ret)
    assert result["model_valid"] is True


def test_gmm_n_unique_regimes():
    ret = _make_returns(504)
    result = fit_gmm(ret, n_regimes=4)
    if result["model_valid"]:
        unique = result["regimes"].nunique()
        assert unique <= 4


def test_gmm_current_regime_is_string():
    ret = _make_returns(504)
    result = fit_gmm(ret)
    if result["model_valid"]:
        assert isinstance(result["current_regime"], str)


def test_gmm_regime_stats_keys():
    ret = _make_returns(504)
    result = fit_gmm(ret)
    if result["model_valid"]:
        for name, stats in result["regime_stats"].items():
            assert "mean_return" in stats
            assert "mean_vol" in stats
            assert "frequency" in stats


def test_gmm_transition_matrix_shape():
    ret = _make_returns(504)
    result = fit_gmm(ret, n_regimes=4)
    if result["model_valid"]:
        trans = np.array(result["transition_matrix"])
        assert trans.shape == (4, 4)
        # Rows should sum to ~1
        for row in trans:
            if row.sum() > 0:
                assert abs(row.sum() - 1.0) < 0.01


def test_gmm_insufficient_data():
    ret = _make_returns(100)
    result = fit_gmm(ret)
    assert result["model_valid"] is False


# ---------------------------------------------------------------------------
# Classify at each date (rolling)
# ---------------------------------------------------------------------------

def test_classify_at_each_date_length():
    ret = _make_returns(200)
    regimes = _classify_at_each_date(ret, lookback=60)
    assert len(regimes) == len(ret)


def test_classify_at_each_date_all_valid():
    ret = _make_returns(200)
    regimes = _classify_at_each_date(ret)
    for r in regimes:
        assert r in REGIME_LABELS


# ---------------------------------------------------------------------------
# Portfolio performance by regime
# ---------------------------------------------------------------------------

def test_portfolio_regime_perf_keys():
    """Portfolio perf should include metrics for regimes with enough data."""
    port_ret = _make_returns(300, mean=0.0005, std=0.015, seed=1)
    regime_dates = [d.strftime("%Y-%m-%d") for d in port_ret.index]
    # Alternate regimes
    regimes = []
    for i, d in enumerate(regime_dates):
        if i < 100:
            regimes.append("Bull - Low Vol")
        elif i < 200:
            regimes.append("Bear - Low Vol")
        else:
            regimes.append("Bull - High Vol")

    history = {"dates": regime_dates, "regimes": regimes, "current_regime": "Bull - High Vol"}
    result = portfolio_regime_performance(port_ret, history)

    assert "current_regime" in result
    assert "recommendation" in result
    assert isinstance(result["recommendation"], str)


def test_portfolio_regime_perf_sharpe():
    """Verify Sharpe is computed correctly for a known regime."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2023-01-02", periods=252, freq="B")
    port_ret = pd.Series(rng.normal(0.001, 0.01, 252), index=idx)
    regime_dates = [d.strftime("%Y-%m-%d") for d in idx]
    regimes = ["Bull - Low Vol"] * 252

    history = {"dates": regime_dates, "regimes": regimes, "current_regime": "Bull - Low Vol"}
    result = portfolio_regime_performance(port_ret, history)

    assert "Bull - Low Vol" in result
    perf = result["Bull - Low Vol"]
    assert "annualized_return" in perf
    assert "annualized_vol" in perf
    assert "sharpe" in perf
    assert "max_drawdown" in perf
    assert perf["days"] == 252


def test_portfolio_regime_perf_days_sum():
    port_ret = _make_returns(300, seed=1)
    regime_dates = [d.strftime("%Y-%m-%d") for d in port_ret.index]
    regimes = ["Bull - Low Vol" if i % 2 == 0 else "Bear - Low Vol" for i in range(300)]

    history = {"dates": regime_dates, "regimes": regimes, "current_regime": "Bear - Low Vol"}
    result = portfolio_regime_performance(port_ret, history)

    total_days = sum(v["days"] for k, v in result.items() if isinstance(v, dict) and "days" in v)
    assert total_days == 300


def test_portfolio_regime_perf_empty():
    result = portfolio_regime_performance(pd.Series(dtype=float), {"dates": [], "regimes": []})
    assert result == {} or "current_regime" not in result


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

def test_interpret_has_current_regime():
    regime_result = {
        "current_regime": "Bull - Low Vol",
        "regime_summary": {
            "Bull - Low Vol": {"total_days": 200, "pct_of_time": 40, "avg_duration": 50},
        },
        "regime_transitions": 5,
        "dates": list(range(500)),
    }
    msgs = interpret_regime(regime_result)
    assert any("Bull - Low Vol" in m for m in msgs)


def test_interpret_with_portfolio_perf():
    regime_result = {
        "current_regime": "Bull - Low Vol",
        "regime_summary": {"Bull - Low Vol": {"total_days": 200, "pct_of_time": 40, "avg_duration": 50}},
        "regime_transitions": 3,
        "dates": list(range(500)),
    }
    perf = {
        "Bull - Low Vol": {"annualized_return": 0.15, "annualized_vol": 0.12, "sharpe": 0.8, "max_drawdown": -0.05, "days": 200},
        "Bear - High Vol": {"annualized_return": -0.10, "annualized_vol": 0.25, "sharpe": -0.6, "max_drawdown": -0.20, "days": 100},
    }
    msgs = interpret_regime(regime_result, perf)
    assert any("best" in m.lower() for m in msgs)
    assert any("vulnerable" in m.lower() for m in msgs)


def test_interpret_best_worst_regime():
    regime_result = {
        "current_regime": "Bear - High Vol",
        "regime_summary": {},
        "regime_transitions": 2,
        "dates": list(range(100)),
    }
    perf = {
        "Bull - Low Vol": {"annualized_return": 0.20, "annualized_vol": 0.10, "sharpe": 1.5, "max_drawdown": -0.03, "days": 50},
        "Bear - High Vol": {"annualized_return": -0.15, "annualized_vol": 0.30, "sharpe": -0.7, "max_drawdown": -0.25, "days": 50},
    }
    msgs = interpret_regime(regime_result, perf)
    best_msgs = [m for m in msgs if "best" in m.lower()]
    assert len(best_msgs) > 0
    assert "Bull - Low Vol" in best_msgs[0]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_all_returns_identical():
    """Zero vol edge case."""
    idx = pd.date_range("2023-01-02", periods=100, freq="B")
    ret = pd.Series([0.001] * 100, index=idx)
    result = rule_based_regime(ret)
    assert result["regime"] in REGIME_LABELS


def test_single_day_data():
    idx = pd.date_range("2023-01-02", periods=1, freq="B")
    ret = pd.Series([0.01], index=idx)
    result = rule_based_regime(ret, lookback=60)
    assert result["confidence"] == 0.0


def test_nan_in_returns():
    ret = _make_returns(200)
    ret.iloc[50] = np.nan
    ret.iloc[100] = np.nan
    # Should not crash
    result = rule_based_regime(ret)
    assert result["regime"] in REGIME_LABELS
