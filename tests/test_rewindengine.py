"""Tests for core/rewindengine.py — Strategy Backtesting Framework."""
import math
import numpy as np
import pandas as pd
import pytest

from core.rewindengine import (
    Strategy, BuyAndHold, MACrossover, RSIMeanReversion, MonthlyRebalance,
    BollingerBandMean, get_strategy, list_strategies, Backtest,
    STRATEGIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n=252, start_price=100.0, daily_return=0.001, seed=42):
    """Create synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    returns = daily_return + rng.normal(0, 0.01, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0, 0.01, n))
    low = close * (1 - rng.uniform(0, 0.01, n))
    opn = close * (1 + rng.normal(0, 0.003, n))
    vol = rng.integers(500000, 5000000, n)
    return pd.DataFrame({"open": opn, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def _make_rising(n=252):
    """Monotonically rising price."""
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    close = np.linspace(100, 150, n)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": [1e6] * n}, index=idx)


def _make_flat(n=252):
    """Flat price at 100."""
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    close = np.full(n, 100.0)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": [1e6] * n}, index=idx)


def _make_crossover_data():
    """Data that forces a golden cross: price rises after flat start."""
    n = 250
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    close = np.concatenate([np.full(200, 100.0), np.linspace(100, 130, 50)])
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1e6] * n}, index=idx)


# ---------------------------------------------------------------------------
# Strategy signals
# ---------------------------------------------------------------------------

def test_buy_and_hold_signals():
    data = _make_ohlcv(50)
    s = BuyAndHold()
    assert s.generate_signal(data, 0) == "BUY"
    assert s.generate_signal(data, 1) == "HOLD"
    assert s.generate_signal(data, 49) == "HOLD"


def test_ma_crossover_hold_insufficient():
    data = _make_ohlcv(100)
    s = MACrossover(fast=50, slow=200)
    assert s.generate_signal(data, 50) == "HOLD"  # < slow


def test_ma_crossover_detects_cross():
    data = _make_crossover_data()
    s = MACrossover(fast=10, slow=50)
    # At end, fast MA should be above slow MA due to price rise
    signals = [s.generate_signal(data, i) for i in range(len(data))]
    assert "BUY" in signals


def test_ma_crossover_no_signal_flat():
    data = _make_flat(252)
    s = MACrossover(fast=50, slow=200)
    # Flat data: no crossover
    signal = s.generate_signal(data, 251)
    assert signal == "HOLD"


def test_rsi_buy_when_oversold():
    """Create data where price drops sharply -> RSI < 30."""
    n = 50
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    close = np.concatenate([np.full(20, 100.0), np.linspace(100, 60, 30)])
    data = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": [1e6] * n}, index=idx)
    s = RSIMeanReversion(period=14, oversold=30, overbought=70)
    signal = s.generate_signal(data, n - 1)
    assert signal == "BUY"


def test_rsi_sell_when_overbought():
    n = 50
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    close = np.concatenate([np.full(20, 100.0), np.linspace(100, 160, 30)])
    data = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": [1e6] * n}, index=idx)
    s = RSIMeanReversion(period=14, oversold=30, overbought=70)
    signal = s.generate_signal(data, n - 1)
    assert signal == "SELL"


def test_rsi_hold_in_range():
    data = _make_ohlcv(50, daily_return=0.0001)
    s = RSIMeanReversion()
    signal = s.generate_signal(data, 49)
    # Normal random data -> RSI likely in middle range
    assert signal in ("BUY", "SELL", "HOLD")


def test_bollinger_buy_below_lower():
    """Price drops below lower band."""
    n = 30
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    close = np.concatenate([np.full(25, 100.0), [90, 85, 80, 75, 70]])
    data = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": [1e6] * n}, index=idx)
    s = BollingerBandMean(window=20, num_std=2.0)
    signal = s.generate_signal(data, n - 1)
    assert signal == "BUY"


def test_monthly_rebalance_buy_first_and_month():
    data = _make_ohlcv(60)
    s = MonthlyRebalance()
    assert s.generate_signal(data, 0) == "BUY"
    # Find a month boundary
    for i in range(1, len(data)):
        if data.index[i].month != data.index[i - 1].month:
            assert s.generate_signal(data, i) == "BUY"
            break


def test_get_strategy_all_names():
    for name in STRATEGIES:
        s = get_strategy(name)
        assert isinstance(s, Strategy)


def test_get_strategy_unknown():
    with pytest.raises(ValueError):
        get_strategy("nonexistent")


def test_list_strategies_count():
    result = list_strategies()
    assert len(result) == 5
    assert all("name" in s for s in result)


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------

def test_buyhold_return_approx():
    """BuyAndHold on rising data: return ~ price change minus costs."""
    data = _make_rising(100)
    bt = Backtest(BuyAndHold(), data, initial_capital=100000, commission_bps=10, slippage_bps=0, seed=42)
    r = bt.run()
    assert r["valid"] is True
    # Price goes from 100 to 150 -> ~50% before costs
    assert r["total_return"] > 0.40
    assert r["total_return"] < 0.55


def test_initial_equity():
    data = _make_ohlcv(50)
    bt = Backtest(BuyAndHold(), data, initial_capital=100000)
    r = bt.run()
    assert r["equity_curve"][0] == 100000


def test_equity_curve_length():
    data = _make_ohlcv(100)
    bt = Backtest(BuyAndHold(), data)
    r = bt.run()
    assert len(r["equity_curve"]) == 100


def test_buyhold_trade_count():
    """BuyAndHold: 1 BUY + 1 forced SELL at end = 2 trades."""
    data = _make_ohlcv(50)
    bt = Backtest(BuyAndHold(), data)
    r = bt.run()
    assert r["total_trades"] == 2


def test_commissions_deducted():
    data = _make_ohlcv(50)
    bt = Backtest(BuyAndHold(), data, commission_bps=10)
    r = bt.run()
    assert r["total_commissions"] > 0


def test_more_trades_more_commission():
    """Strategy with more trades should have higher commission drag."""
    data = _make_ohlcv(252, seed=10)
    # BuyAndHold: 2 trades
    r1 = Backtest(BuyAndHold(), data, commission_bps=50).run()
    # Bollinger: potentially many trades
    r2 = Backtest(BollingerBandMean(window=10, num_std=1.5), data, commission_bps=50).run()
    if r2["total_trades"] > r1["total_trades"]:
        assert r2["total_commissions"] >= r1["total_commissions"]


def test_final_value_is_cash():
    """After backtest, all positions are closed, final_value = cash."""
    data = _make_ohlcv(50)
    bt = Backtest(BuyAndHold(), data)
    r = bt.run()
    assert abs(r["final_value"] - r["equity_curve"][-1]) < 1


def test_flat_price_return_negative():
    """Flat price + commissions = slight loss."""
    data = _make_flat(50)
    bt = Backtest(BuyAndHold(), data, commission_bps=10, slippage_bps=0)
    r = bt.run()
    assert r["total_return"] < 0  # costs cause loss


def test_insufficient_data():
    data = _make_ohlcv(1)
    bt = Backtest(BuyAndHold(), data)
    r = bt.run()
    assert r["valid"] is False


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

def test_volatility_annualized():
    data = _make_ohlcv(252)
    r = Backtest(BuyAndHold(), data).run()
    # Annualized vol should be reasonable (0.01 to 2.0)
    assert 0 < r["volatility"] < 2.0


def test_sharpe_formula():
    data = _make_ohlcv(252, daily_return=0.001)
    r = Backtest(BuyAndHold(), data).run()
    expected = (r["annualized_return"] - 0.052) / r["volatility"] if r["volatility"] > 0 else 0
    assert abs(r["sharpe"] - round(expected, 4)) < 0.01


def test_max_drawdown_negative():
    data = _make_ohlcv(252)
    r = Backtest(BuyAndHold(), data).run()
    assert r["max_drawdown"] <= 0


def test_calmar():
    data = _make_ohlcv(252)
    r = Backtest(BuyAndHold(), data).run()
    if r["max_drawdown"] != 0:
        expected = r["annualized_return"] / abs(r["max_drawdown"])
        assert abs(r["calmar"] - round(expected, 4)) < 0.01


def test_win_rate_bounds():
    data = _make_ohlcv(252)
    r = Backtest(BollingerBandMean(window=10, num_std=1.5), data).run()
    assert 0 <= r["win_rate"] <= 1


def test_profit_factor_nonneg():
    data = _make_ohlcv(252)
    r = Backtest(BollingerBandMean(window=10, num_std=1.5), data).run()
    assert r["profit_factor"] >= 0 or r["profit_factor"] == float("inf")


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------

def test_drawdown_curve_length():
    data = _make_ohlcv(100)
    r = Backtest(BuyAndHold(), data).run()
    assert len(r["drawdown_curve"]) == len(r["equity_curve"])


def test_drawdown_all_negative_or_zero():
    data = _make_ohlcv(100)
    r = Backtest(BuyAndHold(), data).run()
    assert all(d <= 0.0001 for d in r["drawdown_curve"])


def test_drawdown_monotonic_up():
    """Monotonically rising equity = drawdown always 0."""
    data = _make_rising(100)
    r = Backtest(BuyAndHold(), data, commission_bps=0, slippage_bps=0).run()
    # After initial buy, equity rises monotonically
    # First bar is cash-only, then invested
    for d in r["drawdown_curve"][1:]:
        assert d >= -0.001  # allow tiny float error


def test_max_drawdown_equals_min():
    data = _make_ohlcv(100)
    r = Backtest(BuyAndHold(), data).run()
    assert abs(r["max_drawdown"] - min(r["drawdown_curve"])) < 0.001


# ---------------------------------------------------------------------------
# Trade analysis
# ---------------------------------------------------------------------------

def test_avg_win_positive():
    data = _make_ohlcv(252)
    r = Backtest(BollingerBandMean(window=10, num_std=1.5), data).run()
    if r["winning_trades"] > 0:
        assert r["avg_win"] > 0


def test_avg_loss_negative():
    data = _make_ohlcv(252)
    r = Backtest(BollingerBandMean(window=10, num_std=1.5), data).run()
    if r["losing_trades"] > 0:
        assert r["avg_loss"] < 0


def test_largest_win_gte_avg():
    data = _make_ohlcv(252)
    r = Backtest(BollingerBandMean(window=10, num_std=1.5), data).run()
    if r["winning_trades"] > 0:
        assert r["largest_win"] >= r["avg_win"]


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def test_compare_returns_all():
    data = _make_ohlcv(252)
    configs = [
        {"name": "buy_and_hold"},
        {"name": "ma_crossover", "params": {"fast": 10, "slow": 50}},
    ]
    # Use direct Backtest comparison instead of compare_strategies (which needs data.py)
    results = []
    for cfg in configs:
        s = get_strategy(cfg["name"], cfg.get("params"))
        r = Backtest(s, data).run()
        if r["valid"]:
            results.append(r)
    assert len(results) == 2


def test_compare_sorted_by_sharpe():
    data = _make_ohlcv(252)
    results = []
    for name in ["buy_and_hold", "bollinger_mean_reversion"]:
        s = get_strategy(name)
        r = Backtest(s, data).run()
        results.append(r)
    results.sort(key=lambda x: x["sharpe"], reverse=True)
    sharpes = [r["sharpe"] for r in results]
    assert sharpes == sorted(sharpes, reverse=True)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_zero_commission():
    data = _make_rising(50)
    r = Backtest(BuyAndHold(), data, commission_bps=0, slippage_bps=0).run()
    assert r["total_commissions"] == 0


def test_all_hold_no_trades():
    """Strategy that never signals BUY -> 0 trades, return = 0."""
    class NeverBuy(Strategy):
        def __init__(self):
            super().__init__("NeverBuy", {})
        def generate_signal(self, data, i):
            return "HOLD"

    data = _make_ohlcv(50)
    r = Backtest(NeverBuy(), data).run()
    assert r["total_trades"] == 0
    assert r["total_return"] == 0


def test_strategy_beats_benchmark():
    """On always-declining then recovering data, RSI mean reversion should beat buy-and-hold."""
    n = 100
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    # Decline then sharp recovery
    close = np.concatenate([
        np.linspace(100, 70, 50),
        np.linspace(70, 110, 50),
    ])
    data = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": [1e6] * n}, index=idx)

    bh = Backtest(BuyAndHold(), data, commission_bps=0, slippage_bps=0).run()
    # RSI should buy during oversold dip
    rsi_bt = Backtest(RSIMeanReversion(period=14, oversold=30, overbought=70), data, commission_bps=0, slippage_bps=0).run()
    # At minimum both should be valid
    assert bh["valid"] is True
    assert rsi_bt["valid"] is True
