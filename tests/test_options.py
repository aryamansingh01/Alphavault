"""
Comprehensive test suite for options & derivatives pricing engine.
Tests Black-Scholes accuracy, Greeks, implied vol, put-call parity, and payoffs.
"""
import math
import numpy as np
import pytest
from core.options import (
    black_scholes_call, black_scholes_put, put_call_parity_check,
    delta, gamma, theta, vega, rho, all_greeks, implied_volatility,
    call_payoff, put_payoff, straddle_payoff, bull_call_spread_payoff,
    iron_condor_payoff, protective_put_payoff, covered_call_payoff,
    _norm_cdf, _norm_pdf, _d1d2,
)


# ---------------------------------------------------------------------------
# Reference values computed from known BS solutions
# ---------------------------------------------------------------------------
# Standard test case: S=100, K=100, T=1, r=0.05, σ=0.20
# Known BS Call ≈ 10.4506, Put ≈ 5.5735
REF_S, REF_K, REF_T, REF_R, REF_SIGMA = 100.0, 100.0, 1.0, 0.05, 0.20
REF_CALL = 10.4506
REF_PUT = 5.5735


# ===========================================================================
# Normal distribution helpers
# ===========================================================================

class TestNorm:
    def test_cdf_at_zero(self):
        assert _norm_cdf(0) == pytest.approx(0.5, abs=1e-10)

    def test_cdf_symmetry(self):
        assert _norm_cdf(1.0) + _norm_cdf(-1.0) == pytest.approx(1.0, abs=1e-10)

    def test_cdf_extreme_positive(self):
        assert _norm_cdf(6.0) == pytest.approx(1.0, abs=1e-8)

    def test_cdf_extreme_negative(self):
        assert _norm_cdf(-6.0) == pytest.approx(0.0, abs=1e-8)

    def test_pdf_at_zero(self):
        expected = 1.0 / math.sqrt(2 * math.pi)
        assert _norm_pdf(0) == pytest.approx(expected, rel=1e-10)

    def test_pdf_symmetry(self):
        assert _norm_pdf(1.5) == pytest.approx(_norm_pdf(-1.5), rel=1e-10)

    def test_pdf_positive(self):
        for x in [-3, -1, 0, 1, 3]:
            assert _norm_pdf(x) > 0


# ===========================================================================
# Black-Scholes Pricing
# ===========================================================================

class TestBlackScholes:
    def test_call_reference(self):
        c = black_scholes_call(REF_S, REF_K, REF_T, REF_R, REF_SIGMA)
        assert c == pytest.approx(REF_CALL, abs=0.01)

    def test_put_reference(self):
        p = black_scholes_put(REF_S, REF_K, REF_T, REF_R, REF_SIGMA)
        assert p == pytest.approx(REF_PUT, abs=0.01)

    def test_call_always_positive(self):
        for S in [80, 100, 120]:
            for T in [0.1, 0.5, 1.0, 2.0]:
                c = black_scholes_call(S, 100, T, 0.05, 0.20)
                assert c > 0

    def test_put_always_positive(self):
        for S in [80, 100, 120]:
            for T in [0.1, 0.5, 1.0, 2.0]:
                p = black_scholes_put(S, 100, T, 0.05, 0.20)
                assert p > 0

    def test_deep_itm_call_near_intrinsic(self):
        # S=200, K=100, deeply ITM call ≈ S - K*exp(-rT)
        c = black_scholes_call(200, 100, 1.0, 0.05, 0.20)
        lower = 200 - 100 * math.exp(-0.05)  # ≈ 104.88
        assert c >= lower - 0.01

    def test_deep_otm_call_near_zero(self):
        c = black_scholes_call(50, 200, 0.1, 0.05, 0.20)
        assert c < 0.01

    def test_deep_itm_put_near_intrinsic(self):
        p = black_scholes_put(50, 200, 1.0, 0.05, 0.20)
        lower = 200 * math.exp(-0.05) - 50  # ≈ 140.24
        assert p >= lower - 0.1

    def test_call_increases_with_spot(self):
        c1 = black_scholes_call(90, 100, 1.0, 0.05, 0.20)
        c2 = black_scholes_call(110, 100, 1.0, 0.05, 0.20)
        assert c2 > c1

    def test_put_increases_as_spot_falls(self):
        p1 = black_scholes_put(110, 100, 1.0, 0.05, 0.20)
        p2 = black_scholes_put(90, 100, 1.0, 0.05, 0.20)
        assert p2 > p1

    def test_call_increases_with_volatility(self):
        c1 = black_scholes_call(100, 100, 1.0, 0.05, 0.10)
        c2 = black_scholes_call(100, 100, 1.0, 0.05, 0.40)
        assert c2 > c1

    def test_call_increases_with_time(self):
        c1 = black_scholes_call(100, 100, 0.25, 0.05, 0.20)
        c2 = black_scholes_call(100, 100, 2.0, 0.05, 0.20)
        assert c2 > c1

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            black_scholes_call(0, 100, 1.0, 0.05, 0.20)
        with pytest.raises(ValueError):
            black_scholes_call(100, 100, 0, 0.05, 0.20)
        with pytest.raises(ValueError):
            black_scholes_call(100, 100, 1.0, 0.05, 0)


# ===========================================================================
# Put-Call Parity
# ===========================================================================

class TestPutCallParity:
    def test_parity_at_reference(self):
        c = black_scholes_call(REF_S, REF_K, REF_T, REF_R, REF_SIGMA)
        p = black_scholes_put(REF_S, REF_K, REF_T, REF_R, REF_SIGMA)
        residual = put_call_parity_check(c, p, REF_S, REF_K, REF_T, REF_R)
        assert residual == pytest.approx(0.0, abs=1e-8)

    @pytest.mark.parametrize("S,K,T,r,sigma", [
        (100, 100, 1.0, 0.05, 0.20),
        (120, 100, 0.5, 0.03, 0.30),
        (80, 110, 2.0, 0.08, 0.15),
        (150, 80, 0.25, 0.01, 0.50),
        (95, 95, 3.0, 0.04, 0.25),
    ])
    def test_parity_parametrized(self, S, K, T, r, sigma):
        c = black_scholes_call(S, K, T, r, sigma)
        p = black_scholes_put(S, K, T, r, sigma)
        residual = put_call_parity_check(c, p, S, K, T, r)
        assert residual == pytest.approx(0.0, abs=1e-6)


# ===========================================================================
# Greeks
# ===========================================================================

class TestGreeks:
    def test_call_delta_between_0_and_1(self):
        d = delta(100, 100, 1.0, 0.05, 0.20, "call")
        assert 0 < d < 1

    def test_put_delta_between_neg1_and_0(self):
        d = delta(100, 100, 1.0, 0.05, 0.20, "put")
        assert -1 < d < 0

    def test_call_put_delta_relationship(self):
        # Δ_call - Δ_put = 1
        dc = delta(100, 100, 1.0, 0.05, 0.20, "call")
        dp = delta(100, 100, 1.0, 0.05, 0.20, "put")
        assert dc - dp == pytest.approx(1.0, abs=1e-8)

    def test_deep_itm_call_delta_near_one(self):
        d = delta(200, 100, 1.0, 0.05, 0.20, "call")
        assert d > 0.99

    def test_deep_otm_call_delta_near_zero(self):
        d = delta(50, 200, 0.1, 0.05, 0.20, "call")
        assert d < 0.01

    def test_gamma_positive(self):
        g = gamma(100, 100, 1.0, 0.05, 0.20)
        assert g > 0

    def test_gamma_highest_atm(self):
        g_atm = gamma(100, 100, 0.5, 0.05, 0.20)
        g_itm = gamma(120, 100, 0.5, 0.05, 0.20)
        g_otm = gamma(80, 100, 0.5, 0.05, 0.20)
        assert g_atm >= g_itm
        assert g_atm >= g_otm

    def test_theta_negative_for_long(self):
        # Long options lose value over time (mostly)
        th = theta(100, 100, 1.0, 0.05, 0.20, "call")
        assert th < 0

    def test_vega_positive(self):
        v = vega(100, 100, 1.0, 0.05, 0.20)
        assert v > 0

    def test_vega_highest_atm(self):
        v_atm = vega(100, 100, 0.5, 0.05, 0.20)
        v_itm = vega(130, 100, 0.5, 0.05, 0.20)
        v_otm = vega(70, 100, 0.5, 0.05, 0.20)
        assert v_atm >= v_itm
        assert v_atm >= v_otm

    def test_call_rho_positive(self):
        r = rho(100, 100, 1.0, 0.05, 0.20, "call")
        assert r > 0

    def test_put_rho_negative(self):
        r = rho(100, 100, 1.0, 0.05, 0.20, "put")
        assert r < 0

    def test_all_greeks_consistency(self):
        g = all_greeks(100, 100, 1.0, 0.05, 0.20, "call")
        assert g["delta"] == pytest.approx(delta(100, 100, 1.0, 0.05, 0.20, "call"), rel=1e-8)
        assert g["gamma"] == pytest.approx(gamma(100, 100, 1.0, 0.05, 0.20), rel=1e-8)
        assert g["vega"] == pytest.approx(vega(100, 100, 1.0, 0.05, 0.20), rel=1e-8)

    def test_delta_numerical_vs_analytical(self):
        """Delta should approximate dC/dS via finite difference."""
        eps = 0.01
        c_up = black_scholes_call(100 + eps, 100, 1.0, 0.05, 0.20)
        c_dn = black_scholes_call(100 - eps, 100, 1.0, 0.05, 0.20)
        numerical_delta = (c_up - c_dn) / (2 * eps)
        analytical_delta = delta(100, 100, 1.0, 0.05, 0.20, "call")
        assert numerical_delta == pytest.approx(analytical_delta, abs=0.001)

    def test_gamma_numerical(self):
        """Gamma ≈ d²C/dS² via central finite difference."""
        eps = 0.01
        c_up = black_scholes_call(100 + eps, 100, 1.0, 0.05, 0.20)
        c_md = black_scholes_call(100, 100, 1.0, 0.05, 0.20)
        c_dn = black_scholes_call(100 - eps, 100, 1.0, 0.05, 0.20)
        numerical_gamma = (c_up - 2 * c_md + c_dn) / (eps ** 2)
        analytical_gamma = gamma(100, 100, 1.0, 0.05, 0.20)
        assert numerical_gamma == pytest.approx(analytical_gamma, abs=0.01)

    def test_vega_numerical(self):
        """Vega ≈ dC/dσ (per 1% move)."""
        eps = 0.001
        c_up = black_scholes_call(100, 100, 1.0, 0.05, 0.20 + eps)
        c_dn = black_scholes_call(100, 100, 1.0, 0.05, 0.20 - eps)
        numerical_vega = (c_up - c_dn) / (2 * eps) * 0.01
        analytical_vega = vega(100, 100, 1.0, 0.05, 0.20)
        assert numerical_vega == pytest.approx(analytical_vega, abs=0.001)


# ===========================================================================
# Implied Volatility
# ===========================================================================

class TestImpliedVol:
    def test_recovers_known_vol(self):
        c = black_scholes_call(REF_S, REF_K, REF_T, REF_R, REF_SIGMA)
        iv = implied_volatility(c, REF_S, REF_K, REF_T, REF_R, "call")
        assert iv == pytest.approx(REF_SIGMA, abs=0.001)

    def test_recovers_put_vol(self):
        p = black_scholes_put(REF_S, REF_K, REF_T, REF_R, REF_SIGMA)
        iv = implied_volatility(p, REF_S, REF_K, REF_T, REF_R, "put")
        assert iv == pytest.approx(REF_SIGMA, abs=0.001)

    @pytest.mark.parametrize("true_vol", [0.10, 0.20, 0.35, 0.50, 0.80])
    def test_range_of_vols(self, true_vol):
        c = black_scholes_call(100, 100, 1.0, 0.05, true_vol)
        iv = implied_volatility(c, 100, 100, 1.0, 0.05, "call")
        assert iv == pytest.approx(true_vol, abs=0.005)

    def test_otm_option(self):
        c = black_scholes_call(90, 110, 0.5, 0.05, 0.25)
        iv = implied_volatility(c, 90, 110, 0.5, 0.05, "call")
        assert iv == pytest.approx(0.25, abs=0.005)

    def test_itm_put(self):
        p = black_scholes_put(80, 100, 1.0, 0.05, 0.30)
        iv = implied_volatility(p, 80, 100, 1.0, 0.05, "put")
        assert iv == pytest.approx(0.30, abs=0.005)


# ===========================================================================
# Payoff Diagrams
# ===========================================================================

class TestPayoffs:
    @pytest.fixture
    def price_range(self):
        return np.linspace(50, 150, 101)

    def test_long_call_payoff_at_expiry(self, price_range):
        K, prem = 100, 5
        pnl = call_payoff(price_range, K, prem)
        # Below strike: loss = -premium
        assert pnl[0] == pytest.approx(-prem, abs=0.01)
        # At strike: loss = -premium
        idx_at_strike = 50  # price=100
        assert pnl[idx_at_strike] == pytest.approx(-prem, abs=0.01)
        # Above strike: profit increases linearly
        assert pnl[-1] == pytest.approx(150 - 100 - prem, abs=0.01)

    def test_short_call_is_mirror(self, price_range):
        K, prem = 100, 5
        long = call_payoff(price_range, K, prem, "long")
        short = call_payoff(price_range, K, prem, "short")
        np.testing.assert_allclose(long + short, 0.0, atol=1e-10)

    def test_long_put_payoff(self, price_range):
        K, prem = 100, 5
        pnl = put_payoff(price_range, K, prem)
        # At S=50: profit = 100-50-5 = 45
        assert pnl[0] == pytest.approx(45, abs=0.01)
        # Above strike: loss = -premium
        assert pnl[-1] == pytest.approx(-prem, abs=0.01)

    def test_straddle_profitable_both_directions(self, price_range):
        K = 100
        call_p = black_scholes_call(100, K, 0.5, 0.05, 0.25)
        put_p = black_scholes_put(100, K, 0.5, 0.05, 0.25)
        pnl = straddle_payoff(price_range, K, call_p, put_p)
        # Profitable at extremes, max loss at strike
        assert pnl[0] > 0    # far below strike
        assert pnl[-1] > 0   # far above strike
        assert pnl[50] < 0   # at the strike

    def test_bull_call_spread_bounded_profit(self, price_range):
        K_low, K_high = 90, 110
        p_low = black_scholes_call(100, K_low, 0.5, 0.05, 0.25)
        p_high = black_scholes_call(100, K_high, 0.5, 0.05, 0.25)
        pnl = bull_call_spread_payoff(price_range, K_low, K_high, p_low, p_high)
        # Max profit is bounded: (K_high - K_low) - net_premium
        max_profit = (K_high - K_low) - (p_low - p_high)
        assert np.max(pnl) == pytest.approx(max_profit, abs=0.1)

    def test_covered_call_capped_upside(self, price_range):
        S_entry = 100
        K = 110
        prem = black_scholes_call(100, K, 0.5, 0.05, 0.20)
        pnl = covered_call_payoff(price_range, S_entry, K, prem)
        # Above K: profit is capped at K - S_entry + premium
        max_pnl = K - S_entry + prem
        # Check far above K
        assert pnl[-1] == pytest.approx(max_pnl, abs=0.1)

    def test_protective_put_limited_downside(self, price_range):
        S_entry = 100
        K = 95
        prem = black_scholes_put(100, K, 0.5, 0.05, 0.20)
        pnl = protective_put_payoff(price_range, S_entry, K, prem)
        # Max loss is limited: S_entry - K + premium
        max_loss = -(S_entry - K + prem)
        assert pnl[0] == pytest.approx(max_loss, abs=0.1)

    def test_iron_condor_bounded(self, price_range):
        K1, K2, K3, K4 = 80, 90, 110, 120
        p1 = black_scholes_put(100, K1, 0.5, 0.05, 0.20)
        p2 = black_scholes_put(100, K2, 0.5, 0.05, 0.20)
        p3 = black_scholes_call(100, K3, 0.5, 0.05, 0.20)
        p4 = black_scholes_call(100, K4, 0.5, 0.05, 0.20)
        pnl = iron_condor_payoff(price_range, K1, K2, K3, K4, p1, p2, p3, p4)
        # Iron condor has bounded risk
        assert np.max(np.abs(pnl)) < 50  # bounded within reasonable range


# ===========================================================================
# Edge Cases & Robustness
# ===========================================================================

class TestEdgeCases:
    def test_very_short_expiry(self):
        # 1 day to expiry, ATM
        c = black_scholes_call(100, 100, 1/365, 0.05, 0.20)
        assert c > 0
        assert c < 5  # very small time value

    def test_very_long_expiry(self):
        c = black_scholes_call(100, 100, 10.0, 0.05, 0.20)
        assert c > 0

    def test_very_high_volatility(self):
        c = black_scholes_call(100, 100, 1.0, 0.05, 2.0)
        assert c > 0

    def test_very_low_volatility(self):
        c = black_scholes_call(100, 100, 1.0, 0.05, 0.001)
        assert c > 0

    def test_zero_rate(self):
        c = black_scholes_call(100, 100, 1.0, 0.0, 0.20)
        p = black_scholes_put(100, 100, 1.0, 0.0, 0.20)
        # With r=0, C = P for ATM (by symmetry of put-call parity: C - P = S - K = 0)
        assert c == pytest.approx(p, abs=0.01)

    def test_greeks_short_expiry(self):
        g = all_greeks(100, 100, 1/365, 0.05, 0.20, "call")
        assert isinstance(g["delta"], float)
        assert isinstance(g["gamma"], float)
