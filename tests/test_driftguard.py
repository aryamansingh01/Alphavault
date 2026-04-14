"""Tests for core/driftguard.py — Portfolio Rebalancing Engine."""
import pytest

from core.driftguard import (
    calculate_drift, generate_trades, estimate_tax_impact,
    rebalance_needed, suggest_target_weights,
)


# ---------------------------------------------------------------------------
# calculate_drift
# ---------------------------------------------------------------------------

def test_drift_perfectly_balanced():
    current = {"AAPL": 0.5, "MSFT": 0.5}
    target = {"AAPL": 0.5, "MSFT": 0.5}
    result = calculate_drift(current, target)
    assert all(d["action"] == "HOLD" for d in result)
    assert all(abs(d["drift"]) < 0.001 for d in result)


def test_drift_overweight():
    current = {"AAPL": 0.60, "MSFT": 0.40}
    target = {"AAPL": 0.50, "MSFT": 0.50}
    result = calculate_drift(current, target)
    aapl = next(d for d in result if d["ticker"] == "AAPL")
    msft = next(d for d in result if d["ticker"] == "MSFT")
    assert aapl["action"] == "SELL"
    assert msft["action"] == "BUY"
    assert aapl["drift"] > 0
    assert msft["drift"] < 0


def test_drift_missing_in_current():
    """Ticker in target but not current -> needs BUY."""
    current = {"AAPL": 1.0}
    target = {"AAPL": 0.5, "MSFT": 0.5}
    result = calculate_drift(current, target)
    msft = next(d for d in result if d["ticker"] == "MSFT")
    assert msft["action"] == "BUY"
    assert msft["current_weight"] == 0.0


def test_drift_ticker_not_in_target():
    """Ticker in current but not target -> needs SELL entirely."""
    current = {"AAPL": 0.5, "MSFT": 0.5}
    target = {"AAPL": 1.0}
    result = calculate_drift(current, target)
    msft = next(d for d in result if d["ticker"] == "MSFT")
    assert msft["action"] == "SELL"
    assert msft["target_weight"] == 0.0


def test_drift_sorted_by_abs_drift():
    current = {"AAPL": 0.60, "MSFT": 0.30, "GOOGL": 0.10}
    target = {"AAPL": 0.33, "MSFT": 0.33, "GOOGL": 0.34}
    result = calculate_drift(current, target)
    drifts = [abs(d["drift"]) for d in result]
    assert drifts == sorted(drifts, reverse=True)


def test_drift_empty():
    result = calculate_drift({}, {})
    assert result == []


# ---------------------------------------------------------------------------
# generate_trades
# ---------------------------------------------------------------------------

def test_generate_trades_correct_shares():
    drift_table = [
        {"ticker": "AAPL", "action": "SELL", "drift": 0.10, "current_weight": 0.60},
        {"ticker": "MSFT", "action": "BUY", "drift": -0.10, "current_weight": 0.40},
    ]
    prices = {"AAPL": 200.0, "MSFT": 400.0}
    trades = generate_trades(drift_table, 100000, prices)

    aapl = next(t for t in trades if t["ticker"] == "AAPL")
    msft = next(t for t in trades if t["ticker"] == "MSFT")

    # SELL: 0.10 * 100000 = $10000 / $200 = 50 shares, negative
    assert aapl["shares"] == -50
    assert aapl["action"] == "SELL"

    # BUY: 0.10 * 100000 = $10000 / $400 = 25 shares
    assert msft["shares"] == 25
    assert msft["action"] == "BUY"


def test_generate_trades_tiny_drift_skipped():
    drift_table = [
        {"ticker": "AAPL", "action": "BUY", "drift": -0.002, "current_weight": 0.498},
    ]
    prices = {"AAPL": 200.0}
    trades = generate_trades(drift_table, 10000, prices)
    # 0.002 * 10000 = $20 / $200 = 0 shares -> skipped
    assert len(trades) == 0


def test_generate_trades_hold_skipped():
    drift_table = [
        {"ticker": "AAPL", "action": "HOLD", "drift": 0.0, "current_weight": 0.5},
    ]
    trades = generate_trades(drift_table, 100000, {"AAPL": 200.0})
    assert len(trades) == 0


def test_generate_trades_zero_portfolio():
    drift_table = [{"ticker": "AAPL", "action": "BUY", "drift": -0.5, "current_weight": 0.0}]
    trades = generate_trades(drift_table, 0, {"AAPL": 200.0})
    assert trades == []


def test_generate_trades_zero_price():
    drift_table = [{"ticker": "AAPL", "action": "BUY", "drift": -0.5, "current_weight": 0.0}]
    trades = generate_trades(drift_table, 100000, {"AAPL": 0.0})
    assert trades == []


# ---------------------------------------------------------------------------
# estimate_tax_impact
# ---------------------------------------------------------------------------

def test_tax_long_term_gain():
    trades = [{"ticker": "AAPL", "action": "SELL", "shares": -50, "price": 200.0, "dollar_amount": 10000}]
    cost_basis = {"AAPL": 150.0}
    holding_periods = {"AAPL": 400}  # > 365 days
    result = estimate_tax_impact(trades, cost_basis, holding_periods)
    assert result["available"] is True
    # Gain: 50 * (200-150) = $2500, long-term at 15%
    assert result["long_term_gain"] == 2500.0
    assert result["estimated_tax_long"] == 375.0  # 2500 * 0.15


def test_tax_short_term_gain():
    trades = [{"ticker": "MSFT", "action": "SELL", "shares": -10, "price": 420.0, "dollar_amount": 4200}]
    cost_basis = {"MSFT": 350.0}
    holding_periods = {"MSFT": 200}  # < 365 days
    result = estimate_tax_impact(trades, cost_basis, holding_periods)
    assert result["available"] is True
    # Gain: 10 * (420-350) = $700, short-term at 35%
    assert result["short_term_gain"] == 700.0
    assert result["estimated_tax_short"] == 245.0  # 700 * 0.35


def test_tax_sell_at_loss():
    trades = [{"ticker": "AAPL", "action": "SELL", "shares": -10, "price": 100.0, "dollar_amount": 1000}]
    cost_basis = {"AAPL": 150.0}
    holding_periods = {"AAPL": 400}
    result = estimate_tax_impact(trades, cost_basis, holding_periods)
    # Loss: 10 * (100-150) = -$500
    assert result["total_realized_gain"] == -500.0
    # No tax on loss
    assert result["estimated_tax_long"] == 0


def test_tax_no_cost_basis():
    trades = [{"ticker": "AAPL", "action": "SELL", "shares": -10, "price": 200.0, "dollar_amount": 2000}]
    result = estimate_tax_impact(trades)
    assert result["available"] is False


def test_tax_buy_trades_ignored():
    trades = [{"ticker": "AAPL", "action": "BUY", "shares": 10, "price": 200.0, "dollar_amount": 2000}]
    result = estimate_tax_impact(trades, {"AAPL": 150.0}, {"AAPL": 400})
    assert result["available"] is True
    assert result["total_realized_gain"] == 0.0


# ---------------------------------------------------------------------------
# rebalance_needed
# ---------------------------------------------------------------------------

def test_rebalance_within_tolerance():
    current = {"AAPL": 0.52, "MSFT": 0.48}
    target = {"AAPL": 0.50, "MSFT": 0.50}
    result = rebalance_needed(current, target, tolerance=0.05)
    assert result["rebalance_needed"] is False


def test_rebalance_outside_tolerance():
    current = {"AAPL": 0.70, "MSFT": 0.30}
    target = {"AAPL": 0.50, "MSFT": 0.50}
    result = rebalance_needed(current, target, tolerance=0.05)
    assert result["rebalance_needed"] is True
    assert result["positions_out_of_band"] == 2


def test_rebalance_max_drift_ticker():
    current = {"AAPL": 0.70, "MSFT": 0.20, "GOOGL": 0.10}
    target = {"AAPL": 0.33, "MSFT": 0.33, "GOOGL": 0.34}
    result = rebalance_needed(current, target)
    # AAPL has the biggest drift (0.37)
    assert result["max_drift_ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# suggest_target_weights
# ---------------------------------------------------------------------------

def test_suggest_equal_weights():
    result = suggest_target_weights(["AAPL", "MSFT", "GOOGL"], "equal")
    assert len(result["weights"]) == 3
    for w in result["weights"].values():
        assert abs(w - 1/3) < 0.001


def test_suggest_market_cap_fallback():
    result = suggest_target_weights(["AAPL", "MSFT"], "market_cap")
    # Falls back to equal
    assert result["strategy"] == "equal"
    assert "falling back" in result["note"].lower()


def test_suggest_empty_tickers():
    result = suggest_target_weights([])
    assert result["weights"] == {}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_single_position():
    current = {"AAPL": 1.0}
    target = {"AAPL": 1.0}
    result = calculate_drift(current, target)
    assert len(result) == 1
    assert result[0]["action"] == "HOLD"


def test_weights_not_summing_to_one():
    """Should still work even if weights don't sum to 1."""
    current = {"AAPL": 0.3, "MSFT": 0.3}  # sum = 0.6
    target = {"AAPL": 0.5, "MSFT": 0.5}
    result = calculate_drift(current, target)
    aapl = next(d for d in result if d["ticker"] == "AAPL")
    assert aapl["action"] == "BUY"
