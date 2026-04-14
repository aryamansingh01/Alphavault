"""
Pure computation functions for portfolio analytics.
Extracted from API handlers so they can be unit-tested without HTTP/yfinance.
"""
import numpy as np
import math


# ---------------------------------------------------------------------------
# Portfolio risk/return metrics
# ---------------------------------------------------------------------------

def portfolio_returns(price_matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Compute weighted portfolio daily returns from a (T, N) price matrix."""
    individual_returns = np.diff(price_matrix, axis=0) / price_matrix[:-1]
    return individual_returns @ weights


def annualized_return(daily_returns: np.ndarray, trading_days: int = 252) -> float:
    return float(np.mean(daily_returns) * trading_days)


def annualized_volatility(daily_returns: np.ndarray, trading_days: int = 252) -> float:
    return float(np.std(daily_returns, ddof=1) * math.sqrt(trading_days))


def sharpe_ratio(ann_return: float, ann_vol: float, rf: float = 0.052) -> float:
    if ann_vol <= 0:
        return 0.0
    return (ann_return - rf) / ann_vol


def sortino_ratio(daily_returns: np.ndarray, rf: float = 0.052, trading_days: int = 252) -> float:
    neg = daily_returns[daily_returns < 0]
    if len(neg) == 0:
        return 0.0
    downside_vol = float(np.std(neg, ddof=1) * math.sqrt(trading_days))
    ann_ret = annualized_return(daily_returns, trading_days)
    return (ann_ret - rf) / downside_vol if downside_vol > 0 else 0.0


def beta(portfolio_returns: np.ndarray, benchmark_returns: np.ndarray) -> float:
    if len(portfolio_returns) < 20 or len(benchmark_returns) < 20:
        return 1.0
    min_len = min(len(portfolio_returns), len(benchmark_returns))
    p = portfolio_returns[:min_len]
    b = benchmark_returns[:min_len]
    cov_matrix = np.cov(p, b)
    if cov_matrix[1, 1] <= 0:
        return 1.0
    return float(cov_matrix[0, 1] / cov_matrix[1, 1])


def alpha(ann_return: float, beta_val: float, market_ann_return: float, rf: float = 0.052) -> float:
    return ann_return - rf - beta_val * (market_ann_return - rf)


def treynor_ratio(ann_return: float, beta_val: float, rf: float = 0.052) -> float:
    if beta_val == 0:
        return 0.0
    return (ann_return - rf) / beta_val


def max_drawdown(daily_returns: np.ndarray) -> float:
    cum = np.cumprod(1 + daily_returns)
    running_max = np.maximum.accumulate(cum)
    drawdowns = (cum - running_max) / running_max
    return float(np.min(drawdowns))


def calmar_ratio(ann_return: float, max_dd: float) -> float:
    if max_dd == 0:
        return 0.0
    return ann_return / abs(max_dd)


def value_at_risk(daily_returns: np.ndarray, confidence: float = 0.95) -> float:
    percentile = (1 - confidence) * 100
    return float(np.percentile(daily_returns, percentile))


def conditional_var(daily_returns: np.ndarray, var_threshold: float) -> float:
    tail = daily_returns[daily_returns <= var_threshold]
    if len(tail) == 0:
        return var_threshold
    return float(np.mean(tail))


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------

def correlation_matrix(returns_matrix: np.ndarray) -> np.ndarray:
    """Compute correlation matrix from (T, N) daily returns matrix."""
    return np.corrcoef(returns_matrix, rowvar=False)


# ---------------------------------------------------------------------------
# Efficient frontier (Markowitz)
# ---------------------------------------------------------------------------

def solve_min_variance(mu: np.ndarray, cov: np.ndarray, target_ret: float = None) -> np.ndarray:
    """Analytical min-variance portfolio, optionally constrained to a target return.
    Long-only approximation via clipping negatives."""
    n = len(mu)
    try:
        inv_cov = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        return np.ones(n) / n

    ones = np.ones(n)

    if target_ret is None:
        w = inv_cov @ ones
        w = w / w.sum()
    else:
        A = ones @ inv_cov @ ones
        B = ones @ inv_cov @ mu
        C = mu @ inv_cov @ mu
        det = A * C - B * B
        if abs(det) < 1e-12:
            w = inv_cov @ ones / (ones @ inv_cov @ ones)
        else:
            lam1 = (C - target_ret * B) / det
            lam2 = (target_ret * A - B) / det
            w = inv_cov @ (lam1 * ones + lam2 * mu)

    w = np.maximum(w, 0)
    s = w.sum()
    return w / s if s > 0 else np.ones(n) / n


def portfolio_stats(weights: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> tuple:
    """Return (expected annual return, annual volatility) for a given weight vector."""
    r = float(weights @ mu)
    v = float(math.sqrt(max(weights @ cov @ weights, 0)))
    return r, v


def efficient_frontier(mu: np.ndarray, cov: np.ndarray, n_points: int = 40, n_random: int = 500, seed: int = 42):
    """Compute frontier points, min-vol portfolio, and max-sharpe portfolio.
    Returns dict with keys: frontier, min_vol, max_sharpe."""
    n = len(mu)
    cov = cov + np.eye(n) * 1e-8

    # Min-Vol
    w_mv = solve_min_variance(mu, cov)
    r_mv, v_mv = portfolio_stats(w_mv, mu, cov)

    # Max-Sharpe (tangent portfolio)
    try:
        inv_cov = np.linalg.inv(cov)
        w_s = inv_cov @ mu
        w_s = np.maximum(w_s, 0)
        s = w_s.sum()
        w_s = w_s / s if s > 0 else np.ones(n) / n
    except Exception:
        w_s = np.ones(n) / n
    r_s, v_s = portfolio_stats(w_s, mu, cov)

    best_sharpe = r_s / v_s if v_s > 1e-9 else 0
    best_w = w_s.copy()

    frontier = []

    # Analytical sweep
    r_lo = float(mu.min()) * 0.8
    r_hi = float(mu.max()) * 1.2
    for target in np.linspace(r_lo, r_hi, n_points):
        w = solve_min_variance(mu, cov, target_ret=target)
        r, v = portfolio_stats(w, mu, cov)
        if v > 0:
            frontier.append((v, r))
            sh = r / v
            if sh > best_sharpe:
                best_sharpe = sh
                best_w = w.copy()

    # Random portfolios
    rng = np.random.default_rng(seed)
    for _ in range(n_random):
        w = rng.dirichlet(np.ones(n))
        r, v = portfolio_stats(w, mu, cov)
        frontier.append((v, r))
        sh = r / v if v > 1e-9 else 0
        if sh > best_sharpe:
            best_sharpe = sh
            best_w = w.copy()

    w_s = best_w
    r_s, v_s = portfolio_stats(w_s, mu, cov)

    return {
        "frontier": frontier,
        "min_vol": {"weights": w_mv, "ret": r_mv, "vol": v_mv},
        "max_sharpe": {"weights": w_s, "ret": r_s, "vol": v_s,
                       "sharpe": r_s / v_s if v_s > 1e-9 else 0},
    }


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------

def monte_carlo(nav: float, mu_ann: float, vol_ann: float,
                years: int = 20, monthly_contrib: float = 500,
                inflation: float = 0.03, n_sims: int = 1000,
                seed: int = None) -> dict:
    """Run Monte Carlo portfolio projection. Returns percentiles and sample paths."""
    if seed is not None:
        np.random.seed(seed)

    steps = years * 12
    mu_m = mu_ann / 12
    sig_m = vol_ann / math.sqrt(12)

    paths = np.zeros((n_sims, steps + 1))
    paths[:, 0] = nav

    for t in range(1, steps + 1):
        z = np.random.normal(0, 1, n_sims)
        cont = monthly_contrib * (1 + inflation) ** (t / 12)
        paths[:, t] = paths[:, t - 1] * (1 + mu_m + sig_m * z) + cont

    final = paths[:, -1]
    percentiles = {q: float(np.percentile(final, q)) for q in [5, 10, 25, 50, 75, 90, 95]}
    prob_positive = float((final > nav).mean() * 100)

    return {
        "percentiles": percentiles,
        "final_values": final,
        "paths": paths,
        "prob_positive": prob_positive,
        "mu": mu_ann,
        "vol": vol_ann,
    }


# ---------------------------------------------------------------------------
# Stress testing
# ---------------------------------------------------------------------------

SCENARIOS = [
    {"name": "2008 Financial Crisis", "type": "hist", "spy": -0.565},
    {"name": "2020 COVID Crash",       "type": "hist", "spy": -0.340},
    {"name": "2022 Rate Hike Bear",    "type": "hist", "spy": -0.252},
    {"name": "2000 Dot-Com Bust",      "type": "hist", "spy": -0.491},
    {"name": "2018 Q4 Correction",     "type": "hist", "spy": -0.196},
    {"name": "Rising Rates +2%",       "type": "rate",      "shock": 0.02},
    {"name": "Tech Selloff -40%",      "type": "sector",    "shock": -0.40, "sector": "Technology"},
    {"name": "Inflation Spike +5%",    "type": "inflation", "shock": 0.05},
]

SECTORS = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology", "GOOGL": "Technology",
    "META": "Technology", "AMZN": "Consumer", "TSLA": "Consumer", "JNJ": "Healthcare",
    "UNH": "Healthcare", "JPM": "Financials", "XOM": "Energy", "CVX": "Energy",
    "SPY": "Diversified", "QQQ": "Technology", "VTI": "Diversified",
    "BND": "Bonds", "GLD": "Commodities", "IBIT": "Crypto",
}


def stress_test(tickers: list, weights: np.ndarray, betas: dict) -> list:
    """Compute estimated portfolio impact under each stress scenario."""
    results = []
    for sc in SCENARIOS:
        st = sc["type"]
        if st == "hist":
            imp = sum(w * sc["spy"] * betas.get(tk, 1) for w, tk in zip(weights, tickers))
        elif st == "rate":
            imp = sum(w * (-0.05 * sc["shock"] * betas.get(tk, 1)) for w, tk in zip(weights, tickers))
        elif st == "sector":
            imp = sum(w * (sc["shock"] if SECTORS.get(tk, "Other") == sc["sector"] else -0.02)
                      for w, tk in zip(weights, tickers))
        elif st == "inflation":
            imp = sum(w * (-0.03 * sc["shock"]) for w, tk in zip(weights, tickers))
        else:
            imp = 0
        results.append({"scenario": sc["name"], "impact": float(imp), "spy_ref": sc.get("spy")})
    return results


def drawdown_analysis(prices: np.ndarray) -> dict:
    """Compute drawdown stats from a 1-D price series."""
    if len(prices) < 10:
        return {"maxdrawdown": 0, "duration": 0, "calmar": 0}
    peak = np.maximum.accumulate(prices)
    dd = (prices - peak) / peak
    md = float(np.min(dd))
    dur = int(np.sum(dd < -0.001))
    ann = float((prices[-1] / prices[0]) ** (252 / len(prices)) - 1) if len(prices) > 1 else 0
    cal = ann / abs(md) if md != 0 else 0
    return {"maxdrawdown": md, "duration": dur, "calmar": cal, "annualized_return": ann}
