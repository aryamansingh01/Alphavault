"""
Portfolio rebalancing engine.
Tracks weight drift from targets, generates rebalancing trades,
and estimates tax implications of sells.
"""
import math
import numpy as np
from core.sanitize import validate_weights, safe_divide


def calculate_drift(current_weights: dict, target_weights: dict) -> list:
    """Calculate weight drift for each position.

    current_weights: {"AAPL": 0.35, "MSFT": 0.25, "GOOGL": 0.40}
    target_weights: {"AAPL": 0.33, "MSFT": 0.33, "GOOGL": 0.34}

    Returns list of dicts sorted by abs(drift) descending."""
    all_tickers = set(list(current_weights.keys()) + list(target_weights.keys()))
    result = []

    for ticker in all_tickers:
        current = current_weights.get(ticker, 0.0)
        target = target_weights.get(ticker, 0.0)
        drift = current - target
        drift_pct = safe_divide(drift, target) * 100

        if drift < -0.001:
            action = "BUY"
        elif drift > 0.001:
            action = "SELL"
        else:
            action = "HOLD"

        result.append({
            "ticker": ticker,
            "current_weight": round(current, 6),
            "target_weight": round(target, 6),
            "drift": round(drift, 6),
            "drift_pct": round(drift_pct, 2),
            "action": action,
        })

    result.sort(key=lambda x: abs(x["drift"]), reverse=True)
    return result


def generate_trades(drift_table: list, portfolio_value: float, current_prices: dict) -> list:
    """Generate specific trades to rebalance.
    For each position with action BUY or SELL:
    - dollar_amount = abs(drift) * portfolio_value
    - shares = floor(dollar_amount / current_price)
    Skip trades where shares would be 0."""
    if portfolio_value <= 0:
        return []

    trades = []
    for row in drift_table:
        if row["action"] == "HOLD":
            continue

        ticker = row["ticker"]
        price = current_prices.get(ticker, 0)
        if price <= 0:
            continue

        dollar_amount = abs(row["drift"]) * portfolio_value
        shares = math.floor(dollar_amount / price)
        if shares == 0:
            continue

        if row["action"] == "SELL":
            shares = -shares

        actual_dollar = abs(shares) * price
        post_trade_weight = row["current_weight"] + (shares * price / portfolio_value) if portfolio_value > 0 else 0

        trades.append({
            "ticker": ticker,
            "action": row["action"],
            "shares": shares,
            "dollar_amount": round(actual_dollar, 2),
            "price": price,
            "post_trade_weight": round(post_trade_weight, 6),
        })

    return trades


def estimate_tax_impact(trades: list, cost_basis: dict = None, holding_periods: dict = None) -> dict:
    """Estimate tax implications of sell trades.
    cost_basis: avg cost per share. holding_periods: days held.
    Short-term rate: 35%, Long-term rate: 15%."""
    if cost_basis is None or holding_periods is None:
        return {"available": False, "message": "Cost basis data required for tax estimation"}

    SHORT_RATE = 0.35
    LONG_RATE = 0.15

    total_realized = 0.0
    short_term = 0.0
    long_term = 0.0
    tax_short = 0.0
    tax_long = 0.0
    trade_details = []

    for t in trades:
        if t["action"] != "SELL":
            continue

        ticker = t["ticker"]
        basis = cost_basis.get(ticker)
        days = holding_periods.get(ticker)

        if basis is None or days is None:
            continue

        shares_sold = abs(t["shares"])
        gain = shares_sold * (t["price"] - basis)
        total_realized += gain

        if days > 365:
            long_term += gain
            tax = gain * LONG_RATE if gain > 0 else 0
            tax_long += tax
            tax_type = "long_term"
        else:
            short_term += gain
            tax = gain * SHORT_RATE if gain > 0 else 0
            tax_short += tax
            tax_type = "short_term"

        trade_details.append({
            "ticker": ticker,
            "realized_gain": round(gain, 2),
            "tax_type": tax_type,
            "estimated_tax": round(tax, 2),
        })

    return {
        "available": True,
        "total_realized_gain": round(total_realized, 2),
        "short_term_gain": round(short_term, 2),
        "long_term_gain": round(long_term, 2),
        "estimated_tax_short": round(tax_short, 2),
        "estimated_tax_long": round(tax_long, 2),
        "estimated_total_tax": round(tax_short + tax_long, 2),
        "trades": trade_details,
    }


def rebalance_needed(current_weights: dict, target_weights: dict, tolerance: float = 0.05) -> dict:
    """Check if any position has drifted beyond tolerance.
    tolerance: maximum allowed absolute drift (0.05 = 5%)."""
    drift_table = calculate_drift(current_weights, target_weights)

    out_of_band = [d for d in drift_table if abs(d["drift"]) > tolerance]
    max_drift_row = drift_table[0] if drift_table else None

    return {
        "rebalance_needed": len(out_of_band) > 0,
        "max_drift": round(max_drift_row["drift"], 6) if max_drift_row else 0.0,
        "max_drift_ticker": max_drift_row["ticker"] if max_drift_row else "",
        "positions_out_of_band": len(out_of_band),
        "total_positions": len(drift_table),
    }


def suggest_target_weights(tickers: list, strategy: str = "equal") -> dict:
    """Generate target weight suggestions.
    Strategies: 'equal' -> 1/n. 'market_cap' -> falls back to equal with a note."""
    if not tickers:
        return {"strategy": strategy, "weights": {}, "note": "No tickers provided"}

    n = len(tickers)

    if strategy == "market_cap":
        weights = {t.upper(): round(1.0 / n, 6) for t in tickers}
        return {
            "strategy": "equal",
            "weights": weights,
            "note": "Market-cap weighting requires live data; falling back to equal weight",
        }

    weights = {t.upper(): round(1.0 / n, 6) for t in tickers}
    return {"strategy": "equal", "weights": weights, "note": "Equal weight across all positions"}
