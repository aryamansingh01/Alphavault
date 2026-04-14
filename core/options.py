"""
Options & Derivatives pricing engine.
Black-Scholes model, Greeks, implied volatility, and payoff analysis.
"""
import math
import numpy as np


# ---------------------------------------------------------------------------
# Standard normal CDF & PDF (no scipy dependency)
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function (Abramowitz & Stegun approx)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ---------------------------------------------------------------------------
# Black-Scholes core
# ---------------------------------------------------------------------------

def _d1d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple:
    """Compute d1 and d2 for Black-Scholes formula."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        raise ValueError("S, K, T, sigma must be positive")
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European call option price.
    S: spot price, K: strike, T: time to expiry (years), r: risk-free rate, sigma: volatility."""
    d1, d2 = _d1d2(S, K, T, r, sigma)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def black_scholes_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """European put option price via put-call parity."""
    d1, d2 = _d1d2(S, K, T, r, sigma)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def put_call_parity_check(call: float, put: float, S: float, K: float, T: float, r: float) -> float:
    """Returns the parity residual: C - P - S + K*e^(-rT). Should be ≈ 0."""
    return call - put - S + K * math.exp(-r * T)


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------

def delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    d1, _ = _d1d2(S, K, T, r, sigma)
    if option_type == "call":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


def gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Gamma is the same for calls and puts."""
    d1, _ = _d1d2(S, K, T, r, sigma)
    return _norm_pdf(d1) / (S * sigma * math.sqrt(T))


def theta(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """Theta in $/day (divide annual theta by 365)."""
    d1, d2 = _d1d2(S, K, T, r, sigma)
    common = -(S * _norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
    if option_type == "call":
        annual = common - r * K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        annual = common + r * K * math.exp(-r * T) * _norm_cdf(-d2)
    return annual / 365.0


def vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Vega per 1% move in volatility (i.e., multiply by 0.01)."""
    d1, _ = _d1d2(S, K, T, r, sigma)
    return S * _norm_pdf(d1) * math.sqrt(T) * 0.01


def rho(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    """Rho per 1% move in interest rate."""
    _, d2 = _d1d2(S, K, T, r, sigma)
    if option_type == "call":
        return K * T * math.exp(-r * T) * _norm_cdf(d2) * 0.01
    return -K * T * math.exp(-r * T) * _norm_cdf(-d2) * 0.01


def all_greeks(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> dict:
    """Compute all Greeks in one pass."""
    d1, d2 = _d1d2(S, K, T, r, sigma)
    pdf_d1 = _norm_pdf(d1)
    sqrt_T = math.sqrt(T)
    exp_rT = math.exp(-r * T)

    g = pdf_d1 / (S * sigma * sqrt_T)
    v = S * pdf_d1 * sqrt_T * 0.01
    common_theta = -(S * pdf_d1 * sigma) / (2 * sqrt_T)

    if option_type == "call":
        d = _norm_cdf(d1)
        th = (common_theta - r * K * exp_rT * _norm_cdf(d2)) / 365.0
        rh = K * T * exp_rT * _norm_cdf(d2) * 0.01
    else:
        d = _norm_cdf(d1) - 1.0
        th = (common_theta + r * K * exp_rT * _norm_cdf(-d2)) / 365.0
        rh = -K * T * exp_rT * _norm_cdf(-d2) * 0.01

    return {"delta": d, "gamma": g, "theta": th, "vega": v, "rho": rh}


# ---------------------------------------------------------------------------
# Implied Volatility (Newton-Raphson)
# ---------------------------------------------------------------------------

def implied_volatility(market_price: float, S: float, K: float, T: float, r: float,
                       option_type: str = "call", tol: float = 1e-6, max_iter: int = 100) -> float:
    """Solve for implied volatility using Newton-Raphson on vega."""
    sigma = 0.25  # initial guess

    for _ in range(max_iter):
        if option_type == "call":
            price = black_scholes_call(S, K, T, r, sigma)
        else:
            price = black_scholes_put(S, K, T, r, sigma)

        diff = price - market_price
        if abs(diff) < tol:
            return sigma

        d1, _ = _d1d2(S, K, T, r, sigma)
        v = S * _norm_pdf(d1) * math.sqrt(T)
        if v < 1e-12:
            break
        sigma -= diff / v
        sigma = max(sigma, 1e-6)  # keep positive

    return sigma


# ---------------------------------------------------------------------------
# Payoff diagrams
# ---------------------------------------------------------------------------

def call_payoff(S_range: np.ndarray, K: float, premium: float, position: str = "long") -> np.ndarray:
    """Compute call option P&L at expiry across a range of spot prices."""
    intrinsic = np.maximum(S_range - K, 0)
    if position == "long":
        return intrinsic - premium
    return premium - intrinsic  # short call


def put_payoff(S_range: np.ndarray, K: float, premium: float, position: str = "long") -> np.ndarray:
    """Compute put option P&L at expiry across a range of spot prices."""
    intrinsic = np.maximum(K - S_range, 0)
    if position == "long":
        return intrinsic - premium
    return premium - intrinsic  # short put


# ---------------------------------------------------------------------------
# Strategy payoffs
# ---------------------------------------------------------------------------

def straddle_payoff(S_range: np.ndarray, K: float, call_premium: float, put_premium: float) -> np.ndarray:
    """Long straddle: buy call + buy put at same strike."""
    return call_payoff(S_range, K, call_premium) + put_payoff(S_range, K, put_premium)


def bull_call_spread_payoff(S_range: np.ndarray, K_low: float, K_high: float,
                            premium_low: float, premium_high: float) -> np.ndarray:
    """Bull call spread: buy call at K_low, sell call at K_high."""
    return call_payoff(S_range, K_low, premium_low) + call_payoff(S_range, K_high, premium_high, "short")


def iron_condor_payoff(S_range: np.ndarray, K1: float, K2: float, K3: float, K4: float,
                       p1: float, p2: float, p3: float, p4: float) -> np.ndarray:
    """Iron condor: buy put K1, sell put K2, sell call K3, buy call K4 (K1<K2<K3<K4)."""
    return (put_payoff(S_range, K1, p1, "long") +
            put_payoff(S_range, K2, p2, "short") +
            call_payoff(S_range, K3, p3, "short") +
            call_payoff(S_range, K4, p4, "long"))


def protective_put_payoff(S_range: np.ndarray, S_entry: float, K: float, put_premium: float) -> np.ndarray:
    """Protective put: long stock + long put."""
    stock_pnl = S_range - S_entry
    put_pnl = put_payoff(S_range, K, put_premium)
    return stock_pnl + put_pnl


def covered_call_payoff(S_range: np.ndarray, S_entry: float, K: float, call_premium: float) -> np.ndarray:
    """Covered call: long stock + short call."""
    stock_pnl = S_range - S_entry
    short_call = call_payoff(S_range, K, call_premium, "short")
    return stock_pnl + short_call
