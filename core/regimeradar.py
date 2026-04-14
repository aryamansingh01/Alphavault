"""
Market Regime Detection Engine.
Classifies market conditions into interpretable regimes using both
rule-based heuristics and statistical methods (Gaussian Mixture Model).

Regimes:
  - Bull / Low Vol: strong uptrend, calm markets
  - Bull / High Vol: uptrend with turbulence
  - Bear / Low Vol: downtrend, orderly selling
  - Bear / High Vol: crisis/panic conditions
  - Crisis: extreme stress (VIX > 35 or severe drawdown)
"""
import math
import numpy as np
import pandas as pd
from core.sanitize import sanitize_returns, safe_divide, require_min_length

REGIME_LABELS = ["Bull - Low Vol", "Bull - High Vol", "Bear - Low Vol", "Bear - High Vol", "Crisis"]


# ---------------------------------------------------------------------------
# Rule-Based Classification
# ---------------------------------------------------------------------------

def rule_based_regime(spy_returns: pd.Series, vix_level: float = None,
                      yield_slope: float = None, lookback: int = 60) -> dict:
    """Classify current market regime using rule-based heuristics."""
    if spy_returns is None or len(spy_returns) < lookback:
        return {
            "regime": "Bull - Low Vol",
            "confidence": 0.0,
            "metrics": {
                "rolling_return": 0.0, "rolling_vol": 0.0,
                "current_drawdown": 0.0, "vix": vix_level, "yield_slope": yield_slope,
            },
        }

    recent = spy_returns.iloc[-lookback:]
    rolling_ret = float((1 + recent).prod() - 1)
    rolling_vol = float(recent.std() * math.sqrt(252))

    # Drawdown from cumulative returns
    cum = (1 + spy_returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    current_dd = float(dd.iloc[-1])

    metrics = {
        "rolling_return": round(rolling_ret, 4),
        "rolling_vol": round(rolling_vol, 4),
        "current_drawdown": round(current_dd, 4),
        "vix": vix_level,
        "yield_slope": yield_slope,
    }

    # Classification rules (order matters — first match wins)
    if current_dd < -0.20 or (vix_level is not None and vix_level > 35):
        regime = "Crisis"
        confidence = min(1.0, abs(current_dd) / 0.30) if current_dd < -0.20 else min(1.0, vix_level / 50)
    elif rolling_ret < 0 and rolling_vol > 0.20:
        regime = "Bear - High Vol"
        confidence = min(1.0, rolling_vol / 0.30)
    elif rolling_ret < 0 and rolling_vol <= 0.20:
        regime = "Bear - Low Vol"
        confidence = min(1.0, abs(rolling_ret) / 0.10)
    elif rolling_ret >= 0 and rolling_vol > 0.18:
        regime = "Bull - High Vol"
        confidence = min(1.0, rolling_vol / 0.25)
    else:
        regime = "Bull - Low Vol"
        confidence = min(1.0, rolling_ret / 0.15) if rolling_ret > 0 else 0.5

    return {"regime": regime, "confidence": round(max(0, min(1, confidence)), 2), "metrics": metrics}


def _classify_at_each_date(spy_returns: pd.Series, lookback: int = 60) -> pd.Series:
    """Apply rule-based classification at each date (rolling window)."""
    regimes = []
    for i in range(len(spy_returns)):
        if i < lookback:
            regimes.append("Bull - Low Vol")  # default for insufficient history
            continue
        window = spy_returns.iloc[i - lookback:i]
        r = rule_based_regime(spy_returns.iloc[:i + 1], lookback=lookback)
        regimes.append(r["regime"])
    return pd.Series(regimes, index=spy_returns.index)


# ---------------------------------------------------------------------------
# Statistical Classification (Gaussian Mixture Model)
# ---------------------------------------------------------------------------

def fit_gmm(returns: pd.Series, n_regimes: int = 4, random_state: int = 42) -> dict:
    """Fit a Gaussian Mixture Model to identify market regimes statistically."""
    if returns is None or len(returns) < 252:
        return {"model_valid": False, "error": f"Insufficient data: need 252 observations, got {len(returns) if returns is not None else 0}"}

    try:
        from sklearn.mixture import GaussianMixture

        # Feature engineering
        rolling_mean = returns.rolling(21).mean() * 252
        rolling_vol = returns.rolling(21).std() * math.sqrt(252)
        features = pd.DataFrame({"mean": rolling_mean, "vol": rolling_vol}).dropna()

        if len(features) < 100:
            return {"model_valid": False, "error": "Insufficient features after rolling window"}

        X = features.values

        gmm = GaussianMixture(n_components=n_regimes, random_state=random_state, n_init=3)
        gmm.fit(X)
        labels = gmm.predict(X)

        # Map labels to interpretable names
        regime_stats = {}
        for k in range(n_regimes):
            mask = labels == k
            if mask.sum() == 0:
                continue
            regime_stats[k] = {
                "mean_return": float(X[mask, 0].mean()),
                "mean_vol": float(X[mask, 1].mean()),
                "frequency": float(mask.sum() / len(labels)),
            }

        # Sort by mean return to assign names
        sorted_regimes = sorted(regime_stats.keys(), key=lambda k: regime_stats[k]["mean_return"])

        label_map = {}
        n = len(sorted_regimes)
        if n >= 4:
            # Lowest return + higher vol -> Bear - High Vol or Crisis
            label_map[sorted_regimes[0]] = "Bear - High Vol" if regime_stats[sorted_regimes[0]]["mean_vol"] > regime_stats[sorted_regimes[1]]["mean_vol"] else "Bear - Low Vol"
            label_map[sorted_regimes[1]] = "Bear - Low Vol" if sorted_regimes[0] not in label_map or label_map[sorted_regimes[0]] != "Bear - Low Vol" else "Bear - High Vol"
            label_map[sorted_regimes[-1]] = "Bull - Low Vol" if regime_stats[sorted_regimes[-1]]["mean_vol"] < regime_stats[sorted_regimes[-2]]["mean_vol"] else "Bull - High Vol"
            label_map[sorted_regimes[-2]] = "Bull - High Vol" if label_map[sorted_regimes[-1]] == "Bull - Low Vol" else "Bull - Low Vol"
        elif n == 3:
            label_map[sorted_regimes[0]] = "Bear - High Vol"
            label_map[sorted_regimes[1]] = "Bull - High Vol"
            label_map[sorted_regimes[2]] = "Bull - Low Vol"
        elif n == 2:
            label_map[sorted_regimes[0]] = "Bear - High Vol"
            label_map[sorted_regimes[1]] = "Bull - Low Vol"
        elif n == 1:
            label_map[sorted_regimes[0]] = "Bull - Low Vol"

        # Build regime series
        regime_series = pd.Series(
            [label_map.get(l, "Bull - Low Vol") for l in labels],
            index=features.index,
        )

        # Named regime stats
        named_stats = {}
        for k, name in label_map.items():
            named_stats[name] = regime_stats[k]

        # Transition matrix
        trans = np.zeros((n_regimes, n_regimes))
        for i in range(1, len(labels)):
            trans[labels[i - 1], labels[i]] += 1
        row_sums = trans.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        trans = trans / row_sums

        return {
            "regimes": regime_series,
            "current_regime": regime_series.iloc[-1] if len(regime_series) > 0 else "Bull - Low Vol",
            "regime_stats": named_stats,
            "transition_matrix": trans.tolist(),
            "n_observations": len(features),
            "model_valid": True,
        }

    except Exception as e:
        return {"model_valid": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Regime History
# ---------------------------------------------------------------------------

def get_regime_history(period: str = "5y", method: str = "rule_based") -> dict:
    """Compute regime classification over a historical period."""
    try:
        from core.data import get_ohlcv

        spy_df = get_ohlcv("SPY", period)
        if spy_df.empty or "close" not in spy_df.columns:
            return {"error": "Could not fetch SPY data", "dates": [], "regimes": []}

        spy_returns = spy_df["close"].pct_change().dropna()

        if method == "gmm":
            gmm_result = fit_gmm(spy_returns)
            if not gmm_result.get("model_valid", False):
                return {"error": gmm_result.get("error", "GMM failed"), "dates": [], "regimes": []}
            regime_series = gmm_result["regimes"]
        else:
            regime_series = _classify_at_each_date(spy_returns)

        dates = [d.strftime("%Y-%m-%d") for d in regime_series.index]
        regimes = regime_series.tolist()

        # Summary stats
        regime_summary = {}
        for label in REGIME_LABELS:
            mask = regime_series == label
            count = int(mask.sum())
            if count == 0:
                continue
            # Average duration: count consecutive runs
            runs = []
            current_run = 0
            for v in mask:
                if v:
                    current_run += 1
                else:
                    if current_run > 0:
                        runs.append(current_run)
                    current_run = 0
            if current_run > 0:
                runs.append(current_run)

            regime_summary[label] = {
                "total_days": count,
                "pct_of_time": round(count / len(regime_series) * 100, 1),
                "avg_duration": round(np.mean(runs), 1) if runs else 0,
            }

        # Count transitions
        transitions = sum(1 for i in range(1, len(regimes)) if regimes[i] != regimes[i - 1])

        return {
            "dates": dates,
            "regimes": regimes,
            "current_regime": regimes[-1] if regimes else "Bull - Low Vol",
            "regime_summary": regime_summary,
            "regime_transitions": transitions,
            "method": method,
        }

    except Exception as e:
        return {"error": str(e), "dates": [], "regimes": []}


# ---------------------------------------------------------------------------
# Portfolio Performance by Regime
# ---------------------------------------------------------------------------

def portfolio_regime_performance(portfolio_returns: pd.Series, regime_history: dict) -> dict:
    """Compute portfolio performance metrics within each regime."""
    result = {}

    dates = regime_history.get("dates", [])
    regimes = regime_history.get("regimes", [])

    if not dates or not regimes:
        return result

    regime_series = pd.Series(regimes, index=pd.to_datetime(dates))

    # Align
    common = portfolio_returns.index.intersection(regime_series.index)
    if len(common) == 0:
        return result

    aligned_ret = portfolio_returns.loc[common]
    aligned_reg = regime_series.loc[common]

    best_regime = None
    best_return = -np.inf
    worst_regime = None
    worst_return = np.inf

    for label in REGIME_LABELS:
        mask = aligned_reg == label
        if mask.sum() < 5:
            continue

        r = aligned_ret[mask]
        ann_ret = float(r.mean() * 252)
        ann_vol = float(r.std() * math.sqrt(252)) if r.std() > 0 else 0.0
        sharpe = safe_divide(ann_ret - 0.052, ann_vol)

        cum = (1 + r).cumprod()
        peak = cum.cummax()
        dd = ((cum - peak) / peak)
        max_dd = float(dd.min()) if len(dd) > 0 else 0.0

        result[label] = {
            "annualized_return": round(ann_ret, 4),
            "annualized_vol": round(ann_vol, 4),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
            "days": int(mask.sum()),
        }

        if ann_ret > best_return:
            best_return = ann_ret
            best_regime = label
        if ann_ret < worst_return:
            worst_return = ann_ret
            worst_regime = label

    current_regime = regimes[-1] if regimes else "Bull - Low Vol"
    result["current_regime"] = current_regime

    # Find when current regime started
    start_date = dates[-1]
    for i in range(len(regimes) - 2, -1, -1):
        if regimes[i] != current_regime:
            start_date = dates[i + 1]
            break
    else:
        start_date = dates[0]
    result["current_regime_start"] = start_date

    # Recommendation
    if current_regime in result and isinstance(result.get(current_regime), dict):
        perf = result[current_regime]
        if perf["annualized_return"] > 0.05:
            result["recommendation"] = f"Current regime ({current_regime}) historically favorable for this portfolio."
        elif perf["annualized_return"] < -0.05:
            result["recommendation"] = f"Current regime ({current_regime}) historically challenging. Consider defensive positioning."
        else:
            result["recommendation"] = f"Current regime ({current_regime}) shows mixed historical performance."
    else:
        result["recommendation"] = f"Insufficient data to assess portfolio performance in {current_regime}."

    return result


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

def interpret_regime(regime_result: dict, portfolio_perf: dict = None) -> list:
    """Generate human-readable regime insights."""
    insights = []

    current = regime_result.get("current_regime", "unknown")
    insights.append(f"Market is currently in {current} mode.")

    summary = regime_result.get("regime_summary", {})
    if current in summary:
        s = summary[current]
        insights.append(f"This regime has historically lasted {s['avg_duration']:.0f} days on average.")
        insights.append(f"Markets have been in this regime {s['pct_of_time']:.0f}% of the time over the analysis period.")

    if portfolio_perf:
        # Current regime performance
        if current in portfolio_perf and isinstance(portfolio_perf[current], dict):
            ret = portfolio_perf[current]["annualized_return"]
            insights.append(f"Your portfolio's annualized return in {current} is {ret:.1%}.")

        # Best/worst regime
        regime_perfs = {k: v for k, v in portfolio_perf.items()
                        if isinstance(v, dict) and "annualized_return" in v}
        if regime_perfs:
            best = max(regime_perfs, key=lambda k: regime_perfs[k]["annualized_return"])
            worst = min(regime_perfs, key=lambda k: regime_perfs[k]["annualized_return"])
            insights.append(f"Historically, your portfolio performs best in {best} ({regime_perfs[best]['annualized_return']:.1%}).")
            insights.append(f"Your portfolio is most vulnerable in {worst} ({regime_perfs[worst]['annualized_return']:.1%}).")

    # Transition insight
    transitions = regime_result.get("regime_transitions", 0)
    n_dates = len(regime_result.get("dates", []))
    if n_dates > 0 and transitions > 0:
        rate = transitions / max(n_dates, 1) * 252  # annualized
        if rate > 12:
            insights.append(f"Regime instability detected — {transitions} changes over the period. Consider reducing risk.")
        else:
            insights.append(f"Regime has been relatively stable over the analysis period.")

    return insights
