"""
Pair Trading & Cointegration Engine.
Identifies statistically cointegrated pairs, monitors spread z-scores,
and generates mean-reversion trading signals.
"""
import math
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
from itertools import combinations
from core.sanitize import sanitize_returns, require_min_length, safe_divide

# ---------------------------------------------------------------------------
# Half-Life Estimation
# ---------------------------------------------------------------------------

def half_life(spread: pd.Series) -> float:
    """Estimate mean reversion half-life via Ornstein-Uhlenbeck model.
    half_life = -ln(2) / theta, where theta comes from OLS: delta_spread = theta * spread_lag."""
    if spread is None or len(spread) < 10:
        return float("inf")
    try:
        spread_arr = spread.dropna()
        if len(spread_arr) < 10:
            return float("inf")
        lag = spread_arr.shift(1).dropna()
        delta = spread_arr.iloc[1:].values
        lag_vals = lag.values.reshape(-1, 1)
        if len(delta) != len(lag_vals):
            mn = min(len(delta), len(lag_vals))
            delta, lag_vals = delta[:mn], lag_vals[:mn]
        model = sm.OLS(delta - lag.values[:len(delta)], lag_vals).fit()
        theta = model.params[0]
        if theta >= 0:
            return float("inf")
        return -math.log(2) / theta
    except Exception:
        return float("inf")


# ---------------------------------------------------------------------------
# Cointegration Testing
# ---------------------------------------------------------------------------

def test_cointegration(prices_a: pd.Series, prices_b: pd.Series,
                       significance: float = 0.05) -> dict:
    """Test cointegration using Engle-Granger method."""
    if prices_a is None or prices_b is None:
        return {"cointegrated": False, "error": "Missing price data"}
    if len(prices_a) < 60 or len(prices_b) < 60:
        return {"cointegrated": False, "error": "Need at least 60 observations"}

    try:
        # Align
        common = prices_a.index.intersection(prices_b.index)
        a = prices_a.loc[common].dropna()
        b = prices_b.loc[common].dropna()
        common2 = a.index.intersection(b.index)
        a, b = a.loc[common2], b.loc[common2]

        if len(a) < 60:
            return {"cointegrated": False, "error": "Insufficient aligned data"}

        # OLS: a = alpha + beta * b + epsilon
        X = sm.add_constant(b.values)
        model = sm.OLS(a.values, X).fit()
        intercept = float(model.params[0])
        hedge_ratio = float(model.params[1])
        r_squared = float(model.rsquared)

        # ADF test on residuals
        residuals = pd.Series(model.resid, index=common2)
        adf_result = adfuller(residuals, maxlag=1, autolag=None)
        adf_stat = float(adf_result[0])
        p_value = float(adf_result[1])
        crit_vals = {k: float(v) for k, v in adf_result[4].items()}

        hl = half_life(residuals)

        return {
            "cointegrated": p_value < significance,
            "p_value": round(p_value, 6),
            "test_statistic": round(adf_stat, 4),
            "critical_values": crit_vals,
            "hedge_ratio": round(hedge_ratio, 6),
            "intercept": round(intercept, 4),
            "r_squared": round(r_squared, 4),
            "half_life": round(hl, 2) if math.isfinite(hl) else float("inf"),
            "observations": len(a),
        }
    except Exception as e:
        return {"cointegrated": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Pair Discovery
# ---------------------------------------------------------------------------

def find_pairs(price_df: pd.DataFrame, significance: float = 0.05,
               max_pairs: int = 10) -> list:
    """Find all cointegrated pairs from a set of price series."""
    if price_df is None or price_df.empty or price_df.shape[1] < 2:
        return []

    tickers = list(price_df.columns)
    all_pairs = list(combinations(tickers, 2))
    results = []

    for idx, (t_a, t_b) in enumerate(all_pairs):
        if (idx + 1) % 10 == 0 or idx == len(all_pairs) - 1:
            print(f"[PAIRS] Testing pair {idx + 1}/{len(all_pairs)}: {t_a}-{t_b}...")
        res = test_cointegration(price_df[t_a], price_df[t_b], significance)
        if res.get("cointegrated"):
            results.append({
                "ticker_a": t_a,
                "ticker_b": t_b,
                "p_value": res["p_value"],
                "hedge_ratio": res["hedge_ratio"],
                "half_life": res["half_life"],
                "r_squared": res["r_squared"],
            })

    results.sort(key=lambda x: x["p_value"])
    return results[:max_pairs]


# ---------------------------------------------------------------------------
# Spread Analysis
# ---------------------------------------------------------------------------

def calculate_spread(prices_a: pd.Series, prices_b: pd.Series,
                     hedge_ratio: float = None) -> dict:
    """Calculate spread and z-score between two price series."""
    if prices_a is None or prices_b is None:
        return {"error": "Missing price data"}

    common = prices_a.index.intersection(prices_b.index)
    a = prices_a.loc[common].dropna()
    b = prices_b.loc[common].dropna()
    common2 = a.index.intersection(b.index)
    a, b = a.loc[common2], b.loc[common2]

    if len(a) < 10:
        return {"error": "Insufficient data"}

    if hedge_ratio is None:
        X = sm.add_constant(b.values)
        model = sm.OLS(a.values, X).fit()
        hedge_ratio = float(model.params[1])

    spread = a - hedge_ratio * b
    mean_full = float(spread.mean())
    std_full = float(spread.std())

    lookback = min(60, len(spread) // 2)
    if lookback < 5:
        lookback = len(spread)
    rolling_mean = spread.rolling(lookback, min_periods=lookback).mean()
    rolling_std = spread.rolling(lookback, min_periods=lookback).std()
    z_score = (spread - rolling_mean) / rolling_std.replace(0, np.nan)

    current_z = float(z_score.iloc[-1]) if not np.isnan(z_score.iloc[-1]) else 0.0
    valid_z = z_score.dropna()
    pct_above_2 = float((valid_z.abs() > 2).mean() * 100) if len(valid_z) > 0 else 0
    pct_above_1 = float((valid_z.abs() > 1).mean() * 100) if len(valid_z) > 0 else 0

    return {
        "spread": spread,
        "z_score": z_score,
        "current_spread": round(float(spread.iloc[-1]), 4),
        "current_z": round(current_z, 4),
        "mean": round(mean_full, 4),
        "std": round(std_full, 4),
        "hedge_ratio": round(hedge_ratio, 6),
        "min_z": round(float(valid_z.min()), 4) if len(valid_z) > 0 else 0,
        "max_z": round(float(valid_z.max()), 4) if len(valid_z) > 0 else 0,
        "pct_time_above_2": round(pct_above_2, 2),
        "pct_time_above_1": round(pct_above_1, 2),
    }


# ---------------------------------------------------------------------------
# Signal Generation
# ---------------------------------------------------------------------------

def generate_signals(spread_data: dict, entry_z: float = 2.0,
                     exit_z: float = 0.5, stop_z: float = 4.0) -> dict:
    """Generate pair trading signals based on z-score thresholds."""
    cz = spread_data.get("current_z", 0)

    if abs(cz) > stop_z:
        signal = "STOP_LOSS"
        direction = "Close all — spread diverging"
        strength = 5
        desc = f"Spread z-score at {cz:.1f}σ — stop-loss triggered, spread diverging beyond safe range"
    elif cz > entry_z:
        signal = "SHORT_SPREAD"
        direction = "Short A, Long B"
        strength = min(5, int(abs(cz)))
        desc = f"Spread is {cz:.1f}σ above mean — short A, long B for mean reversion"
    elif cz < -entry_z:
        signal = "LONG_SPREAD"
        direction = "Long A, Short B"
        strength = min(5, int(abs(cz)))
        desc = f"Spread is {abs(cz):.1f}σ below mean — long A, short B for mean reversion"
    elif abs(cz) < exit_z:
        signal = "EXIT"
        direction = "Neutral"
        strength = 1
        desc = f"Spread near mean ({cz:.1f}σ) — close any open pair trade"
    else:
        signal = "NO_SIGNAL"
        direction = "Neutral"
        strength = 0
        desc = f"Spread at {cz:.1f}σ — no actionable signal"

    return {
        "signal": signal,
        "current_z": cz,
        "entry_z": entry_z,
        "exit_z": exit_z,
        "stop_z": stop_z,
        "direction": direction,
        "strength": strength,
        "description": desc,
    }


# ---------------------------------------------------------------------------
# Full Pair Analysis
# ---------------------------------------------------------------------------

def analyze_pair(ticker_a: str, ticker_b: str, period: str = "2y") -> dict:
    """Complete pair analysis pipeline for two tickers."""
    try:
        from core.data import get_ohlcv

        df_a = get_ohlcv(ticker_a, period)
        df_b = get_ohlcv(ticker_b, period)

        if df_a.empty or df_b.empty or "close" not in df_a.columns or "close" not in df_b.columns:
            return {"tradeable": False, "error": "Could not fetch price data"}

        pa = df_a["close"]
        pb = df_b["close"]

        coint = test_cointegration(pa, pb)
        if not coint.get("cointegrated"):
            return {
                "ticker_a": ticker_a, "ticker_b": ticker_b,
                "cointegration": coint,
                "tradeable": False,
                "reason": f"Not cointegrated (p={coint.get('p_value', 'N/A')})",
            }

        spread_data = calculate_spread(pa, pb, coint["hedge_ratio"])
        hl = coint["half_life"]
        sig = generate_signals(spread_data)

        return {
            "ticker_a": ticker_a, "ticker_b": ticker_b,
            "cointegration": coint,
            "spread": {
                "current_z": spread_data["current_z"],
                "mean": spread_data["mean"],
                "std": spread_data["std"],
                "hedge_ratio": spread_data["hedge_ratio"],
                "pct_time_above_2": spread_data["pct_time_above_2"],
            },
            "half_life": hl,
            "signal": sig,
            "tradeable": True,
        }
    except Exception as e:
        return {"tradeable": False, "error": str(e)}


def analyze_portfolio_pairs(tickers: list, period: str = "2y",
                            significance: float = 0.05) -> dict:
    """Find and analyze all pairs within a portfolio."""
    if not tickers or len(tickers) < 2:
        return {"pairs_tested": 0, "pairs_found": 0, "pairs": [], "active_signals": []}

    try:
        from core.data import get_ohlcv

        price_df = pd.DataFrame()
        for t in tickers:
            df = get_ohlcv(t, period)
            if not df.empty and "close" in df.columns:
                price_df[t.upper()] = df["close"]

        if price_df.shape[1] < 2:
            return {"pairs_tested": 0, "pairs_found": 0, "pairs": [], "active_signals": []}

        n_tickers = price_df.shape[1]
        n_pairs = n_tickers * (n_tickers - 1) // 2
        found = find_pairs(price_df, significance)

        pair_results = []
        active = []
        for p in found:
            sp = calculate_spread(price_df[p["ticker_a"]], price_df[p["ticker_b"]], p["hedge_ratio"])
            sig = generate_signals(sp)
            z_scores = sp.get("z_score")
            z_list = []
            dates_list = []
            if z_scores is not None and isinstance(z_scores, pd.Series):
                trimmed = z_scores.dropna().iloc[-252:]
                z_list = [round(float(v), 4) if np.isfinite(v) else None for v in trimmed]
                dates_list = [d.strftime("%Y-%m-%d") for d in trimmed.index]

            entry = {
                "ticker_a": p["ticker_a"], "ticker_b": p["ticker_b"],
                "p_value": p["p_value"], "hedge_ratio": p["hedge_ratio"],
                "half_life": p["half_life"],
                "current_z": sp.get("current_z", 0),
                "signal": sig["signal"],
                "tradeable": True,
                "spread_history": {"dates": dates_list, "z_scores": z_list},
            }
            pair_results.append(entry)
            if sig["signal"] in ("LONG_SPREAD", "SHORT_SPREAD"):
                active.append(entry)

        return {
            "pairs_tested": n_pairs,
            "pairs_found": len(found),
            "pairs": pair_results,
            "active_signals": active,
        }
    except Exception as e:
        return {"pairs_tested": 0, "pairs_found": 0, "pairs": [], "active_signals": [], "error": str(e)}
